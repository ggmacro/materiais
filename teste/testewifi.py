"""
testewifi.py

Receptor real para hardware CSI.

Use com um ESP32/ESP32-S3 enviando frames CSI por UDP para este computador.
Este script nao simula dados: se nenhum hardware enviar CSI, ele fica aguardando.

Como rodar no PC:
    python testewifi.py --host 0.0.0.0 --port 5006

Formato UDP aceito:
    {"type":"csi","ts_us":123,"rssi":-55,"len":128,"csi":[1,-2,3,...]}

Tambem tenta aceitar linhas CSV/texto que tenham uma lista CSI no final:
    CSI_DATA,...,[1,-2,3,...]
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import socket
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MAX_WINDOW_SECONDS = 45
MIN_FRAMES_FOR_VITALS = 120
DEFAULT_3D_IMAGE = "csi_3d.svg"
DEFAULT_3D_HTML = "csi_3d.html"
DEFAULT_DASHBOARD_PORT = 8080


@dataclass
class CsiFrame:
    timestamp: float
    rssi: int | None
    csi: list[int]
    source: str


class SharedDashboardState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state = {
            "connected": False,
            "frames": 0,
            "source": "",
            "rssi": None,
            "energy": 0.0,
            "motion": 0.0,
            "presence": False,
            "breathing_bpm": None,
            "heart_bpm": None,
            "breathing_confidence": 0.0,
            "heart_confidence": 0.0,
            "updated_at": 0.0,
            "samples": [],
        }

    def update(self, **values) -> None:
        with self.lock:
            self.state.update(values)

    def snapshot(self) -> dict:
        with self.lock:
            result = dict(self.state)
        result["age_seconds"] = max(0.0, time.time() - float(result.get("updated_at") or 0.0))
        if result["age_seconds"] > 5:
            result["connected"] = False
            result["presence"] = False
        return result


def parse_csi_payload(payload: bytes, source: str) -> CsiFrame | None:
    text = payload.decode("utf-8", errors="ignore").strip()
    if not text:
        return None

    try:
        data = json.loads(text)
        csi = data.get("csi") or data.get("buf") or data.get("data")
        if isinstance(csi, list):
            return CsiFrame(
                timestamp=time.time(),
                rssi=try_int(data.get("rssi")),
                csi=[int(x) for x in csi],
                source=source,
            )
    except json.JSONDecodeError:
        pass

    bracket_match = re.search(r"\[([^\]]+)\]\s*$", text)
    if not bracket_match:
        return None

    csi = [int(x) for x in re.findall(r"-?\d+", bracket_match.group(1))]
    if not csi:
        return None

    rssi = None
    rssi_match = re.search(r"\brssi\b\s*[:=,]\s*(-?\d+)", text, re.IGNORECASE)
    if rssi_match:
        rssi = int(rssi_match.group(1))

    return CsiFrame(timestamp=time.time(), rssi=rssi, csi=csi, source=source)


def try_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def csi_energy(csi: list[int]) -> float:
    """
    Convert interleaved CSI bytes into a compact signal value.

    ESP CSI buffers are usually signed I/Q pairs. We use magnitude energy so the
    code works even when the exact I/Q order varies between firmware versions.
    """
    if len(csi) < 2:
        return 0.0

    pair_count = len(csi) // 2
    total = 0.0
    for i in range(0, pair_count * 2, 2):
        a = csi[i]
        b = csi[i + 1]
        total += math.sqrt(a * a + b * b)

    return total / pair_count


def estimate_bpm(samples: list[tuple[float, float]], min_bpm: int, max_bpm: int) -> tuple[float | None, float]:
    """
    Estimate dominant frequency using a small DFT scan.

    Returns (bpm, confidence). Confidence is a relative peak score, not a
    medical-grade certainty.
    """
    if len(samples) < MIN_FRAMES_FOR_VITALS:
        return None, 0.0

    times = [t for t, _ in samples]
    values = [v for _, v in samples]
    duration = times[-1] - times[0]
    if duration < 12:
        return None, 0.0

    mean_value = statistics.fmean(values)
    centered = [v - mean_value for v in values]
    variance = statistics.fmean([v * v for v in centered])
    if variance <= 1e-9:
        return None, 0.0

    best_bpm = None
    best_power = 0.0
    second_power = 0.0

    for bpm in range(min_bpm, max_bpm + 1):
        hz = bpm / 60.0
        real = 0.0
        imag = 0.0
        for t, value in zip(times, centered):
            phase = 2 * math.pi * hz * (t - times[0])
            real += value * math.cos(phase)
            imag -= value * math.sin(phase)

        power = (real * real + imag * imag) / len(samples)
        if power > best_power:
            second_power = best_power
            best_power = power
            best_bpm = bpm
        elif power > second_power:
            second_power = power

    confidence = best_power / (second_power + 1e-9)
    if confidence < 1.15:
        return None, confidence

    return float(best_bpm), confidence


class HardwareCsiMonitor:
    def __init__(
        self,
        renderer_3d: "Csi3DRenderer | None" = None,
        dashboard_state: SharedDashboardState | None = None,
    ) -> None:
        self.samples: deque[tuple[float, float]] = deque()
        self.baseline: float | None = None
        self.last_print = 0.0
        self.frame_count = 0
        self.renderer_3d = renderer_3d
        self.dashboard_state = dashboard_state

    def add_frame(self, frame: CsiFrame) -> None:
        energy = csi_energy(frame.csi)
        if energy <= 0:
            return

        if self.baseline is None:
            self.baseline = energy
        else:
            self.baseline = 0.995 * self.baseline + 0.005 * energy

        now = frame.timestamp
        self.samples.append((now, energy))
        while self.samples and now - self.samples[0][0] > MAX_WINDOW_SECONDS:
            self.samples.popleft()

        self.frame_count += 1
        if self.renderer_3d:
            self.renderer_3d.add_frame(frame)

        self.update_dashboard(frame, energy)

        if now - self.last_print >= 1.0:
            self.last_print = now
            self.print_status(frame, energy)

    def current_status(self, frame: CsiFrame, energy: float) -> dict:
        baseline = self.baseline or energy
        motion_score = abs(energy - baseline) / max(baseline, 1e-6)
        present = motion_score > 0.015

        sample_list = list(self.samples)
        breathing, breathing_conf = estimate_bpm(sample_list, 6, 30)
        heart, heart_conf = estimate_bpm(sample_list, 45, 130)

        recent_samples = [value for _, value in sample_list[-90:]]
        if recent_samples:
            min_value = min(recent_samples)
            max_value = max(recent_samples)
            span = max(max_value - min_value, 1e-6)
            normalized_samples = [(value - min_value) / span for value in recent_samples]
        else:
            normalized_samples = []

        return {
            "connected": True,
            "frames": self.frame_count,
            "source": frame.source,
            "rssi": frame.rssi,
            "energy": energy,
            "motion": motion_score,
            "presence": present,
            "breathing_bpm": breathing,
            "heart_bpm": heart,
            "breathing_confidence": breathing_conf,
            "heart_confidence": heart_conf,
            "updated_at": time.time(),
            "samples": normalized_samples,
        }

    def update_dashboard(self, frame: CsiFrame, energy: float) -> None:
        if self.dashboard_state:
            self.dashboard_state.update(**self.current_status(frame, energy))

    def print_status(self, frame: CsiFrame, energy: float) -> None:
        status_data = self.current_status(frame, energy)

        breathing = status_data["breathing_bpm"]
        heart = status_data["heart_bpm"]
        breathing_conf = status_data["breathing_confidence"]
        heart_conf = status_data["heart_confidence"]
        motion_score = status_data["motion"]
        present = status_data["presence"]
        breathing_text = f"{breathing:.0f} bpm" if breathing else "calculando"
        heart_text = f"{heart:.0f} bpm" if heart else "calculando"
        rssi_text = str(frame.rssi) if frame.rssi is not None else "?"
        status = "presenca" if present else "calmo"

        print(
            f"frames={self.frame_count:06d} | "
            f"origem={frame.source} | "
            f"rssi={rssi_text} | "
            f"energia={energy:.2f} | "
            f"mov={motion_score:.4f} | "
            f"{status} | "
            f"resp={breathing_text} c={breathing_conf:.2f} | "
            f"bat={heart_text} c={heart_conf:.2f}"
        )


DASHBOARD_HTML = r"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CSI Pose Viewer</title>
  <style>
    html, body {
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #061018;
      color: #eaf6ff;
      font-family: Segoe UI, Arial, sans-serif;
    }
    canvas {
      display: block;
      width: 100vw;
      height: 100vh;
      background: #061018;
    }
    .hud {
      position: fixed;
      left: 22px;
      top: 18px;
      display: grid;
      gap: 8px;
      pointer-events: none;
    }
    .title {
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0;
      text-shadow: 0 0 18px rgba(97, 205, 255, 0.55);
    }
    .metrics {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      max-width: min(720px, calc(100vw - 44px));
    }
    .metric {
      border: 1px solid rgba(156, 220, 255, 0.24);
      background: rgba(8, 22, 32, 0.76);
      padding: 8px 10px;
      min-width: 106px;
      box-sizing: border-box;
    }
    .label {
      color: #9fb8c5;
      font-size: 11px;
      text-transform: uppercase;
    }
    .value {
      color: #f3fbff;
      font-size: 18px;
      font-weight: 650;
      margin-top: 2px;
    }
    .note {
      color: #98adba;
      font-size: 13px;
      max-width: min(640px, calc(100vw - 44px));
      line-height: 1.35;
    }
  </style>
</head>
<body>
  <canvas id="scene"></canvas>
  <div class="hud">
    <div class="title">CSI Pose Viewer</div>
    <div class="metrics">
      <div class="metric"><div class="label">Status</div><div class="value" id="status">aguardando</div></div>
      <div class="metric"><div class="label">Movimento</div><div class="value" id="motion">0.000</div></div>
      <div class="metric"><div class="label">RSSI</div><div class="value" id="rssi">?</div></div>
      <div class="metric"><div class="label">Respiração</div><div class="value" id="breathing">--</div></div>
      <div class="metric"><div class="label">Batimento</div><div class="value" id="heart">--</div></div>
      <div class="metric"><div class="label">Frames</div><div class="value" id="frames">0</div></div>
    </div>
    <div class="note">A silhueta se move a partir de mudanças reais no CSI recebido. Isto não é uma imagem de câmera nem uma reconstrução corporal calibrada.</div>
  </div>
  <script>
    const canvas = document.getElementById("scene");
    const ctx = canvas.getContext("2d");
    const els = {
      status: document.getElementById("status"),
      motion: document.getElementById("motion"),
      rssi: document.getElementById("rssi"),
      breathing: document.getElementById("breathing"),
      heart: document.getElementById("heart"),
      frames: document.getElementById("frames"),
    };

    let state = {
      connected: false,
      presence: false,
      motion: 0,
      rssi: null,
      breathing_bpm: null,
      heart_bpm: null,
      frames: 0,
      samples: [],
    };
    let smoothMotion = 0;
    let phase = 0;

    function resize() {
      const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
      canvas.width = Math.floor(innerWidth * dpr);
      canvas.height = Math.floor(innerHeight * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    addEventListener("resize", resize);
    resize();

    async function pollState() {
      try {
        const response = await fetch("/state.json", { cache: "no-store" });
        state = await response.json();
        updateHud();
      } catch (error) {
        state.connected = false;
        updateHud();
      }
    }

    function updateHud() {
      const active = state.connected && state.presence;
      els.status.textContent = active ? "presença" : state.connected ? "calmo" : "aguardando";
      els.motion.textContent = Number(state.motion || 0).toFixed(3);
      els.rssi.textContent = state.rssi === null ? "?" : state.rssi;
      els.breathing.textContent = state.breathing_bpm ? Math.round(state.breathing_bpm) + " bpm" : "--";
      els.heart.textContent = state.heart_bpm ? Math.round(state.heart_bpm) + " bpm" : "--";
      els.frames.textContent = state.frames || 0;
    }

    function glowLine(x1, y1, x2, y2, color, width) {
      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = 16;
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
      ctx.restore();
    }

    function glowCircle(x, y, radius, color, fillAlpha = 0.18) {
      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = 22;
      ctx.strokeStyle = color;
      ctx.fillStyle = color.replace(")", `, ${fillAlpha})`).replace("rgb", "rgba");
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }

    function drawRoom(w, h) {
      const gradient = ctx.createLinearGradient(0, 0, w, h);
      gradient.addColorStop(0, "#07121d");
      gradient.addColorStop(0.54, "#102634");
      gradient.addColorStop(1, "#15130c");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, w, h);

      const horizon = h * 0.58;
      ctx.strokeStyle = "rgba(150, 220, 255, 0.12)";
      ctx.lineWidth = 1;
      for (let i = -10; i <= 10; i++) {
        const x = w / 2 + i * 70;
        ctx.beginPath();
        ctx.moveTo(w / 2, horizon);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let i = 0; i < 12; i++) {
        const y = horizon + i * i * 5.3;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      ctx.strokeStyle = "rgba(78, 190, 255, 0.16)";
      for (let i = 0; i < 4; i++) {
        const radius = 80 + i * 42;
        ctx.beginPath();
        ctx.ellipse(w * 0.22, h * 0.68, radius, radius * 0.28, 0, Math.PI, Math.PI * 2);
        ctx.stroke();
      }
    }

    function drawWaveform(w, h) {
      const samples = Array.isArray(state.samples) ? state.samples : [];
      if (samples.length < 2) return;
      const x0 = w * 0.06;
      const y0 = h * 0.86;
      const width = Math.min(w * 0.38, 520);
      const height = 90;
      ctx.save();
      ctx.strokeStyle = "rgba(130, 220, 255, 0.76)";
      ctx.shadowColor = "rgba(130, 220, 255, 0.9)";
      ctx.shadowBlur = 14;
      ctx.lineWidth = 2;
      ctx.beginPath();
      samples.forEach((value, index) => {
        const x = x0 + (index / (samples.length - 1)) * width;
        const y = y0 - (Number(value) - 0.5) * height;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.restore();
    }

    function drawWifiArcs(w, h, intensity) {
      ctx.save();
      ctx.strokeStyle = `rgba(77, 191, 255, ${0.22 + intensity * 0.45})`;
      ctx.lineWidth = 8;
      ctx.shadowColor = "rgba(77, 191, 255, 0.85)";
      ctx.shadowBlur = 18;
      for (let i = 0; i < 4; i++) {
        ctx.beginPath();
        ctx.arc(w * 0.52, h * 0.24, 80 + i * 48, Math.PI * 1.13, Math.PI * 1.87);
        ctx.stroke();
      }
      ctx.restore();
    }

    function drawAvatar(w, h, motion) {
      const active = state.connected && state.presence;
      const scale = Math.min(w, h) / 740;
      const cx = w * 0.54;
      const floor = h * 0.76;
      const bob = Math.sin(phase * 2) * motion * 22 * scale;
      const sway = Math.sin(phase) * motion * 28 * scale;
      const color = active ? "rgb(78, 255, 142)" : "rgb(90, 160, 185)";
      const hot = active ? "rgb(255, 82, 58)" : "rgb(110, 190, 220)";

      const head = { x: cx + sway * 0.25, y: floor - 332 * scale + bob };
      const neck = { x: cx, y: floor - 275 * scale + bob };
      const chest = { x: cx + sway * 0.12, y: floor - 230 * scale + bob };
      const hip = { x: cx - sway * 0.10, y: floor - 130 * scale + bob };
      const leftShoulder = { x: neck.x - 58 * scale, y: neck.y + 28 * scale };
      const rightShoulder = { x: neck.x + 58 * scale, y: neck.y + 28 * scale };
      const leftHip = { x: hip.x - 42 * scale, y: hip.y };
      const rightHip = { x: hip.x + 42 * scale, y: hip.y };

      const armSwing = Math.sin(phase) * (48 + 80 * motion) * scale;
      const legSwing = Math.sin(phase) * (64 + 95 * motion) * scale;

      const leftElbow = { x: leftShoulder.x - 38 * scale - armSwing * 0.55, y: leftShoulder.y + 70 * scale };
      const rightElbow = { x: rightShoulder.x + 38 * scale + armSwing * 0.55, y: rightShoulder.y + 70 * scale };
      const leftHand = { x: leftElbow.x - 26 * scale - armSwing * 0.30, y: leftElbow.y + 78 * scale };
      const rightHand = { x: rightElbow.x + 26 * scale + armSwing * 0.30, y: rightElbow.y + 78 * scale };

      const leftKnee = { x: leftHip.x - legSwing * 0.45, y: leftHip.y + 95 * scale };
      const rightKnee = { x: rightHip.x + legSwing * 0.45, y: rightHip.y + 95 * scale };
      const leftFoot = { x: leftKnee.x - legSwing * 0.45, y: floor };
      const rightFoot = { x: rightKnee.x + legSwing * 0.45, y: floor };

      ctx.save();
      ctx.globalAlpha = active ? 1 : 0.48;
      ctx.lineJoin = "round";

      glowCircle(head.x, head.y, 34 * scale, color, 0.10);
      glowLine(neck.x, neck.y, chest.x, chest.y, color, 5 * scale);
      glowLine(chest.x, chest.y, hip.x, hip.y, color, 6 * scale);
      glowLine(leftShoulder.x, leftShoulder.y, rightShoulder.x, rightShoulder.y, color, 5 * scale);
      glowLine(leftHip.x, leftHip.y, rightHip.x, rightHip.y, color, 5 * scale);

      [[leftShoulder, leftElbow], [leftElbow, leftHand], [rightShoulder, rightElbow],
       [rightElbow, rightHand], [leftHip, leftKnee], [leftKnee, leftFoot],
       [rightHip, rightKnee], [rightKnee, rightFoot]].forEach(([a, b]) => {
        glowLine(a.x, a.y, b.x, b.y, color, 5 * scale);
      });

      [leftShoulder, rightShoulder, leftElbow, rightElbow, leftHand, rightHand,
       chest, hip, leftKnee, rightKnee, leftFoot, rightFoot].forEach((p, index) => {
        glowCircle(p.x, p.y, (index < 2 ? 8 : 6) * scale, index % 3 === 0 ? hot : color, 0.28);
      });

      ctx.restore();
    }

    function draw() {
      const w = innerWidth;
      const h = innerHeight;
      smoothMotion += (Math.min(1, Number(state.motion || 0) * 16) - smoothMotion) * 0.08;
      phase += 0.035 + smoothMotion * 0.16;

      drawRoom(w, h);
      drawWifiArcs(w, h, smoothMotion);
      drawAvatar(w, h, smoothMotion);
      drawWaveform(w, h);

      requestAnimationFrame(draw);
    }

    setInterval(pollState, 250);
    pollState();
    draw();
  </script>
</body>
</html>
"""


def start_dashboard_server(host: str, port: int, dashboard_state: SharedDashboardState) -> ThreadingHTTPServer:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path in ("/", "/index.html", "/pose_viewer.html"):
                body = DASHBOARD_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path.startswith("/state.json"):
                body = json.dumps(dashboard_state.snapshot()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_error(404)

        def log_message(self, format: str, *args) -> None:
            return

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class Csi3DRenderer:
    """
    Turns real CSI frames into a 3D-looking signal surface.

    X axis: CSI subcarrier/sample bin
    Y axis: time
    Z axis: signal magnitude
    """

    def __init__(
        self,
        image_path: Path,
        html_path: Path,
        history: int = 70,
        bins: int = 64,
        interval_seconds: float = 2.0,
    ) -> None:
        self.image_path = image_path
        self.html_path = html_path
        self.history = history
        self.bins = bins
        self.interval_seconds = interval_seconds
        self.rows: deque[list[float]] = deque(maxlen=history)
        self.last_render = 0.0

    def add_frame(self, frame: CsiFrame) -> None:
        row = self.csi_to_row(frame.csi)
        if not row:
            return

        self.rows.append(row)
        now = time.time()
        if now - self.last_render >= self.interval_seconds:
            self.last_render = now
            self.render(frame)

    def csi_to_row(self, csi: list[int]) -> list[float]:
        magnitudes = []
        pair_count = len(csi) // 2
        for i in range(0, pair_count * 2, 2):
            real = csi[i]
            imag = csi[i + 1]
            magnitudes.append(math.sqrt(real * real + imag * imag))

        if not magnitudes:
            return []

        if len(magnitudes) <= self.bins:
            return magnitudes

        row = []
        step = len(magnitudes) / self.bins
        for bin_index in range(self.bins):
            start = int(bin_index * step)
            end = int((bin_index + 1) * step)
            chunk = magnitudes[start:max(end, start + 1)]
            row.append(statistics.fmean(chunk))
        return row

    def render(self, frame: CsiFrame) -> None:
        if len(self.rows) < 3:
            return

        svg = self.build_svg(frame)
        self.image_path.write_text(svg, encoding="utf-8")
        self.html_path.write_text(self.build_html(frame), encoding="utf-8")

    def build_svg(self, frame: CsiFrame) -> str:
        width = 1200
        height = 780
        margin_top = 70

        rows = list(self.rows)
        min_value = min(min(row) for row in rows)
        max_value = max(max(row) for row in rows)
        span = max(max_value - min_value, 1e-6)

        def normalized(value: float) -> float:
            return (value - min_value) / span

        def project(x_index: int, y_index: int, value: float) -> tuple[float, float, float]:
            x_count = max(len(rows[0]) - 1, 1)
            y_count = max(len(rows) - 1, 1)
            x = (x_index / x_count - 0.5) * 760
            y = (y_index / y_count - 0.5) * 430
            z = normalized(value) * 260

            screen_x = width / 2 + x - y * 0.62
            screen_y = margin_top + 470 + y * 0.38 - z
            return screen_x, screen_y, z

        def color_for(value: float) -> str:
            z = normalized(value)
            hue = 210 - z * 165
            lightness = 44 + z * 18
            return f"hsl({hue:.0f}, 88%, {lightness:.0f}%)"

        lines = []

        for y_index, row in enumerate(rows):
            points = []
            for x_index, value in enumerate(row):
                x, y, _ = project(x_index, y_index, value)
                points.append(f"{x:.1f},{y:.1f}")
            avg = statistics.fmean(row)
            lines.append(
                f'<polyline points="{" ".join(points)}" '
                f'fill="none" stroke="{color_for(avg)}" stroke-width="2.1" '
                f'stroke-linejoin="round" stroke-linecap="round" opacity="0.88"/>'
            )

        column_step = max(1, len(rows[0]) // 16)
        for x_index in range(0, len(rows[0]), column_step):
            points = []
            for y_index, row in enumerate(rows):
                x, y, _ = project(x_index, y_index, row[x_index])
                points.append(f"{x:.1f},{y:.1f}")
            lines.append(
                f'<polyline points="{" ".join(points)}" '
                'fill="none" stroke="rgba(255,255,255,0.20)" stroke-width="1.1" '
                'stroke-linejoin="round" stroke-linecap="round"/>'
            )

        now = time.strftime("%H:%M:%S")
        rssi = frame.rssi if frame.rssi is not None else "?"
        title = html.escape("Imagem 3D CSI - Wi-Fi sensing")

        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#071018"/>
      <stop offset="55%" stop-color="#10232f"/>
      <stop offset="100%" stop-color="#16140d"/>
    </linearGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="2.2" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <text x="42" y="48" fill="#eef7ff" font-family="Segoe UI, Arial, sans-serif" font-size="28" font-weight="700">{title}</text>
  <text x="42" y="78" fill="#b8ccd8" font-family="Segoe UI, Arial, sans-serif" font-size="15">
    X=subportadoras CSI | Y=tempo | Z=intensidade | frames={len(rows)} | rssi={rssi} | atualizado={now}
  </text>
  <g opacity="0.45">
    <line x1="235" y1="642" x2="980" y2="642" stroke="#d7eefc" stroke-width="1"/>
    <line x1="235" y1="642" x2="122" y2="562" stroke="#d7eefc" stroke-width="1"/>
    <line x1="235" y1="642" x2="235" y2="342" stroke="#d7eefc" stroke-width="1"/>
    <text x="982" y="648" fill="#c7d9e2" font-family="Segoe UI, Arial" font-size="13">subportadoras</text>
    <text x="52" y="558" fill="#c7d9e2" font-family="Segoe UI, Arial" font-size="13">tempo</text>
    <text x="202" y="334" fill="#c7d9e2" font-family="Segoe UI, Arial" font-size="13">intensidade</text>
  </g>
  <g filter="url(#glow)">
    {chr(10).join(lines)}
  </g>
  <text x="42" y="742" fill="#93a8b3" font-family="Segoe UI, Arial, sans-serif" font-size="13">
    Aviso: isto e uma superficie 3D dos dados CSI reais, nao uma reconstrução corporal 3D calibrada.
  </text>
</svg>
"""

    def build_html(self, frame: CsiFrame) -> str:
        image_name = html.escape(self.image_path.name)
        timestamp = time.strftime("%H:%M:%S")
        return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="3">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CSI 3D</title>
  <style>
    body {{
      margin: 0;
      background: #071018;
      color: #eaf6ff;
      font-family: Segoe UI, Arial, sans-serif;
    }}
    main {{
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 20px;
      box-sizing: border-box;
    }}
    img {{
      width: min(100%, 1200px);
      height: auto;
      border: 1px solid rgba(255, 255, 255, 0.14);
      background: #071018;
    }}
    p {{
      width: min(100%, 1200px);
      color: #9fb6c3;
      font-size: 14px;
      margin: 10px 0 0;
    }}
  </style>
</head>
<body>
  <main>
    <div>
      <img src="{image_name}?t={int(time.time())}" alt="Imagem tridimensional CSI">
      <p>Atualizado as {timestamp}. A pagina recarrega automaticamente a cada 3 segundos.</p>
    </div>
  </main>
</body>
</html>
"""


def run_udp_receiver(
    host: str,
    port: int,
    renderer_3d: Csi3DRenderer | None,
    dashboard_state: SharedDashboardState | None,
) -> None:
    monitor = HardwareCsiMonitor(renderer_3d=renderer_3d, dashboard_state=dashboard_state)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(2.0)

    print("Receptor CSI real iniciado.")
    print(f"Escutando UDP em {host}:{port}")
    print("Aguardando ESP32/ESP32-S3 enviar frames CSI...")
    if renderer_3d:
        print(f"Imagem 3D: {renderer_3d.image_path}")
        print(f"Pagina 3D: {renderer_3d.html_path}")

    last_wait_message = time.time()
    while True:
        try:
            payload, address = sock.recvfrom(8192)
        except socket.timeout:
            if time.time() - last_wait_message >= 5:
                last_wait_message = time.time()
                print("Ainda aguardando hardware CSI...")
            continue

        frame = parse_csi_payload(payload, f"{address[0]}:{address[1]}")
        if frame is None:
            continue
        monitor.add_frame(frame)


def main() -> None:
    parser = argparse.ArgumentParser(description="Receptor real de CSI via UDP para ESP32/ESP32-S3.")
    parser.add_argument("--host", default="0.0.0.0", help="IP local para escutar.")
    parser.add_argument("--port", type=int, default=5006, help="Porta UDP para receber CSI.")
    parser.add_argument("--no-3d", action="store_true", help="Desativa a geracao da imagem 3D.")
    parser.add_argument("--image3d", default=DEFAULT_3D_IMAGE, help="Arquivo SVG da imagem 3D.")
    parser.add_argument("--html3d", default=DEFAULT_3D_HTML, help="Arquivo HTML para visualizar a imagem 3D.")
    parser.add_argument("--history3d", type=int, default=70, help="Quantidade de frames usados na superficie 3D.")
    parser.add_argument("--bins3d", type=int, default=64, help="Quantidade de bins/subportadoras no eixo X.")
    parser.add_argument("--no-dashboard", action="store_true", help="Desativa o viewer de silhueta em movimento.")
    parser.add_argument("--dashboard-host", default="127.0.0.1", help="IP do dashboard local.")
    parser.add_argument("--dashboard-port", type=int, default=DEFAULT_DASHBOARD_PORT, help="Porta do dashboard local.")
    args = parser.parse_args()

    renderer_3d = None
    if not args.no_3d:
        renderer_3d = Csi3DRenderer(
            image_path=Path(args.image3d),
            html_path=Path(args.html3d),
            history=args.history3d,
            bins=args.bins3d,
        )

    dashboard_state = None
    dashboard_server = None
    if not args.no_dashboard:
        dashboard_state = SharedDashboardState()
        dashboard_server = start_dashboard_server(args.dashboard_host, args.dashboard_port, dashboard_state)
        print(f"Viewer de pessoas em movimento: http://{args.dashboard_host}:{args.dashboard_port}")

    try:
        run_udp_receiver(args.host, args.port, renderer_3d, dashboard_state)
    finally:
        if dashboard_server:
            dashboard_server.shutdown()


if __name__ == "__main__":
    main()
