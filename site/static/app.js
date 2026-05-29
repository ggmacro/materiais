const state = {
  materials: [],
  lastSimulation: null,
};

const rowsEl = document.querySelector("#compositionRows");
const rowTemplate = document.querySelector("#rowTemplate");
const addRowButton = document.querySelector("#addRowButton");
const runButton = document.querySelector("#runButton");
const materialSearch = document.querySelector("#materialSearch");
const metricsGrid = document.querySelector("#metricsGrid");
const articlesList = document.querySelector("#articlesList");
const statusText = document.querySelector("#statusText");
const researchQuery = document.querySelector("#researchQuery");
const queryLink = document.querySelector("#queryLink");
const atomicCanvas = document.querySelector("#atomicCanvas");
const crystalCanvas = document.querySelector("#crystalCanvas");
const propertyChart = document.querySelector("#propertyChart");
const xrdChart = document.querySelector("#xrdChart");
const xrdImage = document.querySelector("#xrdImage");

const metricLabels = {
  formula_aproximada: "Formula aproximada",
  densidade_g_cm3: "Densidade (g/cm3)",
  modulo_elastico_gpa: "Modulo elastico (GPa)",
  condutividade_termica_w_mk: "Condutividade termica (W/mK)",
  condutividade_eletrica_s_m: "Condutividade eletrica (S/m)",
  resistividade_ohm_m: "Resistividade (ohm m)",
  band_gap_ev: "Band gap (eV)",
  ponto_fusao_c: "Ponto de fusao (C)",
  raio_atomico_pm: "Raio atomico medio (pm)",
  eletronegatividade_media: "Eletronegatividade media",
  dureza_vickers_hv: "Dureza Vickers estimada (HV)",
  seebeck_uv_k: "Coeficiente Seebeck (uV/K)",
  fator_potencia_w_mk2: "Fator de potencia (W/mK2)",
  zt_300k: "ZT estimado em 300 K",
  estrutura_predominante: "Estrutura predominante",
  classe_eletrica: "Classe eletrica",
  indicacao: "Indicacao",
};

const chartMetrics = [
  ["density_g_cm3", "Densidade"],
  ["elastic_modulus_gpa", "Modulo"],
  ["thermal_conductivity_w_mk", "Cond. termica"],
  ["electrical_conductivity_s_m", "Cond. eletrica"],
  ["hardness_vickers_hv", "Dureza HV"],
  ["melting_point_c", "Fusao"],
  ["seebeck_uv_k", "Seebeck"],
  ["zt_300k", "ZT 300K"],
];

function materialText(material) {
  return [
    material.id,
    material.name,
    material.formula,
    material.symbol,
    material.category,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function filteredMaterials(selectedId = "") {
  const query = materialSearch?.value.trim().toLowerCase() || "";
  const selected = state.materials.find((material) => material.id === selectedId);
  let materials = state.materials;

  if (query) {
    materials = state.materials.filter((material) => materialText(material).includes(query));
  }

  if (selected && !materials.some((material) => material.id === selected.id)) {
    materials = [selected, ...materials];
  }

  return materials;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Erro na requisicao.");
  }
  return data;
}

function setStatus(message) {
  statusText.textContent = message;
}

function addRow(materialId, fraction = 0.5) {
  const row = rowTemplate.content.firstElementChild.cloneNode(true);
  const select = row.querySelector(".material-select");
  const input = row.querySelector(".fraction-input");
  const removeButton = row.querySelector(".remove-button");

  const initialMaterial = materialId || state.materials[0]?.id || "";
  fillMaterialSelect(select, initialMaterial);
  input.value = fraction;
  removeButton.addEventListener("click", () => {
    row.remove();
    if (!rowsEl.children.length) {
      addRow();
    }
  });

  rowsEl.append(row);
}

function fillMaterialSelect(select, selectedId = "") {
  const previous = selectedId || select.value;
  select.innerHTML = "";

  for (const material of filteredMaterials(previous)) {
    const option = document.createElement("option");
    option.value = material.id;
    option.textContent = `${material.symbol || material.formula} - ${material.name}`;
    select.append(option);
  }

  if (previous && [...select.options].some((option) => option.value === previous)) {
    select.value = previous;
  }
}

function refreshMaterialSelects() {
  for (const select of rowsEl.querySelectorAll(".material-select")) {
    fillMaterialSelect(select, select.value);
  }
}

function getComposition() {
  const composition = {};
  for (const row of rowsEl.querySelectorAll(".row")) {
    const material = row.querySelector(".material-select").value;
    const fraction = Number(row.querySelector(".fraction-input").value);
    if (!material || Number.isNaN(fraction) || fraction <= 0) {
      continue;
    }
    composition[material] = (composition[material] || 0) + fraction;
  }
  return composition;
}

function formatValue(value) {
  if (typeof value !== "number") {
    return value;
  }
  if (Math.abs(value) >= 100000 || Math.abs(value) < 0.001) {
    return value.toExponential(3);
  }
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 4 });
}

function renderMetrics(simulation) {
  metricsGrid.innerHTML = "";
  for (const [key, value] of Object.entries(simulation)) {
    if (key === "componentes" || key === "xrd") {
      continue;
    }
    const card = document.createElement("article");
    card.className = key === "indicacao" ? "metric metric-wide" : "metric";
    card.innerHTML = `<span>${metricLabels[key] || key}</span><strong>${formatValue(value)}</strong>`;
    metricsGrid.append(card);
  }
}

function renderArticles(articles) {
  articlesList.innerHTML = "";

  if (!articles.length) {
    articlesList.innerHTML =
      '<div class="empty">Nenhum artigo encontrado para esta combinacao.</div>';
    return;
  }

  for (const article of articles) {
    const item = document.createElement("article");
    item.className = "article";

    const authors = article.authors?.length ? article.authors.join(", ") : "Autores nao informados";
    const source = article.source || "Fonte nao informada";
    const doi = article.doi ? `DOI: ${article.doi}` : "Sem DOI";
    const citations = `${article.citations || 0} citacoes`;

    item.innerHTML = `
      <div class="article-provider">${article.provider}</div>
      <a href="${article.url || "#"}" target="_blank" rel="noreferrer">${article.title}</a>
      <div class="article-meta">${authors}</div>
      <div class="article-meta">${article.year || "Ano desconhecido"} - ${source} - ${doi} - ${citations}</div>
    `;
    articlesList.append(item);
  }
}

function clearCanvas(canvas) {
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  return ctx;
}

function drawAtomicJunction(components) {
  const ctx = clearCanvas(atomicCanvas);
  const atoms = [];
  const totalAtoms = 90;

  components.forEach((component) => {
    const count = Math.max(3, Math.round(component.fraction * totalAtoms));
    for (let i = 0; i < count; i += 1) {
      atoms.push(component);
    }
  });

  atoms.forEach((component, index) => {
    const col = index % 15;
    const row = Math.floor(index / 15);
    const jitterX = Math.sin(index * 1.7) * 8;
    const jitterY = Math.cos(index * 2.1) * 8;
    const x = 45 + col * 45 + jitterX;
    const y = 48 + row * 45 + jitterY;
    const radius = Math.max(9, Math.min(22, component.atomic_radius_pm / 8));

    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fillStyle = component.color || "#8fa3ad";
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "rgba(20, 30, 30, 0.25)";
    ctx.stroke();

    ctx.fillStyle = "#18201f";
    ctx.font = "700 11px Arial";
    ctx.textAlign = "center";
    ctx.fillText(component.symbol || component.formula, x, y + 4);
  });

  ctx.fillStyle = "#66716d";
  ctx.font = "13px Arial";
  ctx.textAlign = "left";
  ctx.fillText("Distribuicao aproximada por fracao e raio atomico", 18, atomicCanvas.height - 16);
}

function latticePoints(structure) {
  const points = [];
  const base = [
    [0, 0], [1, 0], [0, 1], [1, 1],
  ];

  if (structure.includes("fcc")) {
    points.push(...base, [0.5, 0.5], [0.5, 0], [0, 0.5], [1, 0.5], [0.5, 1]);
  } else if (structure.includes("bcc")) {
    points.push(...base, [0.5, 0.5]);
  } else if (structure.includes("hcp") || structure.includes("hexagonal")) {
    points.push([0.15, 0.2], [0.5, 0.05], [0.85, 0.2], [0.85, 0.65], [0.5, 0.85], [0.15, 0.65], [0.5, 0.42]);
  } else if (structure.includes("diamante")) {
    points.push(...base, [0.25, 0.25], [0.75, 0.75], [0.25, 0.75], [0.75, 0.25]);
  } else if (structure.includes("ortorrombica")) {
    points.push([0.10, 0.18], [0.42, 0.18], [0.78, 0.18], [0.22, 0.50], [0.58, 0.50], [0.90, 0.50], [0.10, 0.82], [0.42, 0.82], [0.78, 0.82]);
  } else {
    points.push([0.18, 0.22], [0.48, 0.12], [0.78, 0.28], [0.24, 0.62], [0.58, 0.55], [0.82, 0.78], [0.42, 0.86]);
  }
  return points;
}

function drawCrystal(simulation) {
  const ctx = clearCanvas(crystalCanvas);
  const components = simulation.componentes || [];
  const structure = String(simulation.estrutura_predominante || "amorfa").toLowerCase();
  const points = latticePoints(structure);
  const cells = [
    [55, 48], [240, 48], [425, 48],
    [145, 190], [330, 190], [515, 190],
  ];

  cells.forEach(([originX, originY], cellIndex) => {
    ctx.strokeStyle = "rgba(17, 97, 91, 0.32)";
    ctx.lineWidth = 2;
    ctx.strokeRect(originX, originY, 120, 120);

    points.forEach(([px, py], pointIndex) => {
      const component = components[(pointIndex + cellIndex) % Math.max(components.length, 1)] || {};
      const x = originX + px * 120;
      const y = originY + py * 120;
      ctx.beginPath();
      ctx.arc(x, y, 11, 0, Math.PI * 2);
      ctx.fillStyle = component.color || "#8fa3ad";
      ctx.fill();
      ctx.strokeStyle = "rgba(30, 35, 33, 0.25)";
      ctx.stroke();
    });
  });

  ctx.fillStyle = "#1d2321";
  ctx.font = "700 16px Arial";
  ctx.fillText(`Estrutura: ${simulation.estrutura_predominante}`, 18, 24);
  ctx.fillStyle = "#66716d";
  ctx.font = "13px Arial";
  ctx.fillText("Representacao simplificada da celula/rede dominante", 18, crystalCanvas.height - 16);
}

function normalizedValue(value, values) {
  const positives = values.filter((item) => item > 0);
  const max = Math.max(...positives, 1);
  if (max > 100000) {
    return Math.log10(Math.max(value, 1e-12)) / Math.log10(max);
  }
  return value / max;
}

function drawPropertyChart(components) {
  const ctx = clearCanvas(propertyChart);
  const left = 150;
  const top = 35;
  const rowHeight = 52;
  const chartWidth = propertyChart.width - left - 40;

  ctx.fillStyle = "#1d2321";
  ctx.font = "700 16px Arial";
  ctx.fillText("Barras normalizadas por propriedade", 18, 22);

  chartMetrics.forEach(([key, label], rowIndex) => {
    const y = top + rowIndex * rowHeight;
    const values = components.map((component) => Number(component[key]) || 0);
    ctx.fillStyle = "#66716d";
    ctx.font = "13px Arial";
    ctx.fillText(label, 18, y + 18);

    components.forEach((component, index) => {
      const width = normalizedValue(values[index], values) * (chartWidth / components.length - 12);
      const x = left + index * (chartWidth / components.length);
      ctx.fillStyle = component.color || "#8fa3ad";
      ctx.fillRect(x, y, Math.max(2, width), 24);
      ctx.fillStyle = "#1d2321";
      ctx.font = "11px Arial";
      ctx.fillText(component.symbol || component.formula, x, y + 42);
    });
  });
}

function drawXrdChart(xrd) {
  const ctx = clearCanvas(xrdChart);
  const peaks = xrd?.picos || [];
  const left = 54;
  const right = 24;
  const top = 28;
  const bottom = 44;
  const width = xrdChart.width - left - right;
  const height = xrdChart.height - top - bottom;

  ctx.strokeStyle = "#d9ded8";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i += 1) {
    const y = top + (height / 5) * i;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + width, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "#1d2321";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(left, top);
  ctx.lineTo(left, top + height);
  ctx.lineTo(left + width, top + height);
  ctx.stroke();

  peaks.forEach((peak) => {
    const x = left + ((peak.two_theta_deg - 5) / 90) * width;
    const barHeight = (peak.relative_intensity / 100) * height;
    ctx.strokeStyle = peak.color || "#11615b";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x, top + height);
    ctx.lineTo(x, top + height - barHeight);
    ctx.stroke();

    if (peak.relative_intensity > 35) {
      ctx.save();
      ctx.translate(x + 4, top + height - barHeight - 4);
      ctx.rotate(-Math.PI / 4);
      ctx.fillStyle = "#1d2321";
      ctx.font = "11px Arial";
      ctx.fillText(`${peak.symbol} ${peak.hkl}`, 0, 0);
      ctx.restore();
    }
  });

  ctx.fillStyle = "#66716d";
  ctx.font = "12px Arial";
  ctx.fillText("2 theta (graus)", left + width / 2 - 38, xrdChart.height - 12);
  ctx.save();
  ctx.translate(16, top + height / 2 + 38);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText("Intensidade relativa", 0, 0);
  ctx.restore();

  for (let t = 10; t <= 90; t += 20) {
    const x = left + ((t - 5) / 90) * width;
    ctx.fillText(String(t), x - 6, top + height + 18);
  }
}

function drawXrdImage(xrd) {
  const ctx = clearCanvas(xrdImage);
  const peaks = xrd?.picos || [];
  const cx = xrdImage.width / 2;
  const cy = xrdImage.height / 2;
  const maxRadius = Math.min(cx, cy) - 28;

  const gradient = ctx.createRadialGradient(cx, cy, 8, cx, cy, maxRadius);
  gradient.addColorStop(0, "#f7f5ef");
  gradient.addColorStop(1, "#1d2321");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, xrdImage.width, xrdImage.height);

  peaks.forEach((peak) => {
    const radius = 24 + ((peak.two_theta_deg - 5) / 90) * maxRadius;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.strokeStyle = peak.color || "#e85d3f";
    ctx.globalAlpha = 0.18 + Math.min(0.7, peak.relative_intensity / 140);
    ctx.lineWidth = 1 + peak.relative_intensity / 22;
    ctx.stroke();
  });

  ctx.globalAlpha = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, 7, 0, Math.PI * 2);
  ctx.fillStyle = "#ffffff";
  ctx.fill();

  ctx.fillStyle = "#ffffff";
  ctx.font = "13px Arial";
  ctx.fillText("Imagem sintetica de aneis de difracao", 18, xrdImage.height - 18);
}

function renderVisuals(simulation) {
  state.lastSimulation = simulation;
  drawAtomicJunction(simulation.componentes || []);
  drawCrystal(simulation);
  drawPropertyChart(simulation.componentes || []);
  drawXrdChart(simulation.xrd);
  drawXrdImage(simulation.xrd);
}

async function runSimulation() {
  const composition = getComposition();
  if (!Object.keys(composition).length) {
    setStatus("Adicione pelo menos um material com fracao maior que zero.");
    return;
  }

  runButton.disabled = true;
  setStatus("Simulando composicao e buscando artigos...");

  try {
    const [simulationData, researchData] = await Promise.all([
      api("/api/simulate", {
        method: "POST",
        body: JSON.stringify({ composition }),
      }),
      api("/api/research", {
        method: "POST",
        body: JSON.stringify({ composition, query: researchQuery.value }),
      }),
    ]);

    renderMetrics(simulationData.simulation);
    renderVisuals(simulationData.simulation);
    renderArticles(researchData.results);

    const searchUrl = `https://openalex.org/works?page=1&filter=default.search:${encodeURIComponent(
      researchData.query
    )}`;
    queryLink.href = searchUrl;
    setStatus(`Busca usada: ${researchData.query}`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    runButton.disabled = false;
  }
}

async function init() {
  setStatus("Carregando materiais...");
  const data = await api("/api/materials");
  state.materials = data.materials;

  addRow("aluminio", 0.55);
  addRow("cobre", 0.25);
  addRow("silicio", 0.20);
  setStatus("Pronto para simular.");
  await runSimulation();
}

addRowButton.addEventListener("click", () => addRow());
runButton.addEventListener("click", runSimulation);
materialSearch?.addEventListener("input", refreshMaterialSelects);
window.addEventListener("resize", () => {
  if (state.lastSimulation) {
    renderVisuals(state.lastSimulation);
  }
});
init().catch((error) => setStatus(error.message));
