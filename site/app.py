from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from material_simulator import (
    LOCAL_MATERIALS,
    MaterialsProjectClient,
    canonicalize_composition,
    local_material_key,
    simulate_composite,
)


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

SEARCH_TERMS = {
    "aluminio": "aluminum aluminium Al",
    "cobre": "copper Cu",
    "silicio": "silicon Si",
    "vidro": "soda lime glass silicate",
    "grafite": "graphite carbon C",
    "aco": "carbon steel Fe C",
    "hidrogenio": "hydrogen H",
    "carbono": "carbon graphite C",
    "grafeno": "graphene carbon nanomaterial C",
    "magnesio": "magnesium Mg",
    "titanio": "titanium Ti",
    "vanadio": "vanadium V",
    "cromo": "chromium Cr",
    "manganes": "manganese Mn",
    "ferro": "iron Fe",
    "cobalto": "cobalt Co",
    "niquel": "nickel Ni",
    "zinco": "zinc Zn",
    "galio": "gallium Ga",
    "germanio": "germanium Ge",
    "prata": "silver Ag",
    "estanho": "tin Sn",
    "tungstenio": "tungsten W",
    "ouro": "gold Au",
    "mercurio": "mercury Hg",
    "chumbo": "lead Pb",
    "fosforo_negro": "black phosphorus phosphorene P",
    "bismuto": "bismuth Bi",
    "tecnecio": "technetium Tc",
    "telureto_bismuto": "bismuth telluride Bi2Te3 thermoelectric",
    "telureto_chumbo": "lead telluride PbTe thermoelectric semiconductor",
    "telureto_cadmio": "cadmium telluride CdTe photovoltaic semiconductor",
    "telureto_estanho": "tin telluride SnTe topological crystalline insulator",
    "seleneto_estanho": "tin selenide SnSe orthorhombic thermoelectric",
    "selenato_estanho": "tin selenate SnSeO4 inorganic salt crystal",
    "seleneto_estanho_2": "tin diselenide SnSe2 layered semiconductor",
    "sulfeto_molibdenio": "molybdenum disulfide MoS2 layered semiconductor",
    "sulfeto_tungstenio": "tungsten disulfide WS2 layered semiconductor",
    "nitreto_boro": "hexagonal boron nitride h-BN 2D ceramic",
    "oxido_estanho": "tin oxide SnO2 transparent conducting oxide",
    "oxido_zinco": "zinc oxide ZnO wurtzite semiconductor",
    "dioxido_titanio": "titanium dioxide TiO2 rutile anatase photocatalyst",
    "arseneto_galio": "gallium arsenide GaAs III-V semiconductor",
    "fosfeto_indio": "indium phosphide InP III-V semiconductor",
    "latao": "brass Cu Zn alloy",
    "bronze": "bronze Cu Sn alloy",
    "aco_inoxidavel_304": "304 stainless steel Fe Cr Ni alloy",
    "inconel_718": "Inconel 718 nickel superalloy",
    "solda_sn_pb": "SnPb solder eutectic tin lead alloy",
    "abs": "ABS polymer acrylonitrile butadiene styrene",
    "pla": "PLA polylactic acid polymer",
    "pet": "PET polyethylene terephthalate polymer",
    "peek": "PEEK polyether ether ketone polymer",
    "ptfe": "PTFE Teflon fluoropolymer",
    "poliimida": "polyimide high temperature polymer",
    "alumina": "alumina aluminum oxide Al2O3",
    "carbeto_silicio": "silicon carbide SiC",
}

SEARCH_TERMS.update(
    {
        "oxido_escandio": "scandium oxide Sc2O3 rare earth oxide",
        "oxido_itrio": "yttrium oxide Y2O3 rare earth oxide",
        "oxido_lantanio": "lanthanum oxide La2O3 rare earth oxide",
        "oxido_cerio": "cerium oxide ceria CeO2 rare earth oxide",
        "oxido_praseodimio": "praseodymium oxide Pr6O11 rare earth oxide",
        "oxido_neodimio": "neodymium oxide Nd2O3 rare earth oxide",
        "oxido_promecio": "promethium oxide Pm2O3 rare earth oxide",
        "oxido_samario": "samarium oxide Sm2O3 rare earth oxide",
        "oxido_europio": "europium oxide Eu2O3 rare earth phosphor",
        "oxido_gadolinio": "gadolinium oxide Gd2O3 rare earth oxide",
        "oxido_terbio": "terbium oxide Tb4O7 rare earth phosphor",
        "oxido_disprosio": "dysprosium oxide Dy2O3 rare earth oxide",
        "oxido_holmio": "holmium oxide Ho2O3 rare earth oxide",
        "oxido_erbio": "erbium oxide Er2O3 rare earth optical",
        "oxido_tulio": "thulium oxide Tm2O3 rare earth oxide",
        "oxido_iterbio": "ytterbium oxide Yb2O3 rare earth oxide",
        "oxido_lutecio": "lutetium oxide Lu2O3 rare earth oxide",
        "iman_ndfeb": "neodymium iron boron NdFeB permanent magnet",
        "iman_smco": "samarium cobalt SmCo permanent magnet",
    }
)


def json_response(handler: BaseHTTPRequestHandler, data: Any, status: int = 200) -> None:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw)


def fetch_json(url: str, timeout: int = 12) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MaterialResearchApp/1.0 (local prototype)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def material_catalog() -> list[dict[str, Any]]:
    return [
        {"id": key, **material.to_dict()}
        for key, material in sorted(LOCAL_MATERIALS.items())
    ]


def search_openalex(query: str, limit: int = 8) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "search": query,
            "per-page": limit,
            "select": "id,display_name,publication_year,doi,primary_location,authorships,cited_by_count",
        }
    )
    url = f"https://api.openalex.org/works?{params}"
    data = fetch_json(url)
    results = []

    for item in data.get("results", []):
        authors = [
            author.get("author", {}).get("display_name")
            for author in item.get("authorships", [])[:3]
            if author.get("author", {}).get("display_name")
        ]
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        results.append(
            {
                "provider": "OpenAlex",
                "title": item.get("display_name") or "Sem titulo",
                "year": item.get("publication_year"),
                "doi": normalize_doi(item.get("doi")),
                "url": location.get("landing_page_url") or item.get("id"),
                "source": source.get("display_name"),
                "authors": authors,
                "citations": item.get("cited_by_count", 0),
            }
        )

    return results


def search_crossref(query: str, limit: int = 8) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "query.bibliographic": query,
            "rows": limit,
            "select": "title,DOI,URL,issued,container-title,author,is-referenced-by-count",
        }
    )
    url = f"https://api.crossref.org/works?{params}"
    data = fetch_json(url)
    items = data.get("message", {}).get("items", [])
    results = []

    for item in items:
        authors = []
        for author in item.get("author", [])[:3]:
            name = " ".join(
                part for part in [author.get("given"), author.get("family")] if part
            )
            if name:
                authors.append(name)

        year = None
        date_parts = item.get("issued", {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

        title = item.get("title") or ["Sem titulo"]
        container = item.get("container-title") or []
        results.append(
            {
                "provider": "Crossref",
                "title": title[0],
                "year": year,
                "doi": normalize_doi(item.get("DOI")),
                "url": item.get("URL"),
                "source": container[0] if container else None,
                "authors": authors,
                "citations": item.get("is-referenced-by-count", 0),
            }
        )

    return results


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("https://doi.org/", "").strip()


def build_research_query(composition: dict[str, float], custom_query: str = "") -> str:
    composition, compound_message = canonicalize_composition(composition)
    material_terms = []
    for name in composition:
        key = local_material_key(name)
        material = LOCAL_MATERIALS.get(key)
        if material:
            material_terms.append(SEARCH_TERMS.get(key, f"{material.name} {material.formula}"))
        else:
            material_terms.append(name)
    base = " ".join(material_terms)
    if compound_message:
        base = f"{base} orthorhombic layered crystal"
    if custom_query.strip():
        return f"{base} {custom_query.strip()}"
    return f"{base} composite material mechanical thermal electrical test"


def run_research_search(query: str, limit: int = 8) -> dict[str, Any]:
    errors = []
    results = []

    for provider, searcher in [
        ("OpenAlex", search_openalex),
        ("Crossref", search_crossref),
    ]:
        try:
            results.extend(searcher(query, limit=limit))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"{provider}: {exc}")

    seen = set()
    unique_results = []
    for result in results:
        key = result.get("doi") or result.get("url") or result.get("title")
        if key in seen:
            continue
        seen.add(key)
        unique_results.append(result)

    unique_results.sort(key=lambda item: (item.get("year") or 0, item.get("citations") or 0), reverse=True)
    return {"query": query, "results": unique_results[:limit], "errors": errors}


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/materials":
            json_response(self, {"materials": material_catalog()})
            return

        if parsed.path == "/api/search":
            params = urllib.parse.parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            if not query:
                json_response(self, {"error": "Informe uma busca em q."}, status=400)
                return
            json_response(self, run_research_search(query))
            return

        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        try:
            payload = read_json(self)
        except json.JSONDecodeError:
            json_response(self, {"error": "JSON invalido."}, status=400)
            return

        if parsed.path == "/api/simulate":
            composition = payload.get("composition") or {}
            if not isinstance(composition, dict) or not composition:
                json_response(self, {"error": "Envie composition com material: fracao."}, status=400)
                return
            try:
                result = simulate_composite(composition, MaterialsProjectClient())
            except Exception as exc:
                json_response(self, {"error": str(exc)}, status=400)
                return
            json_response(self, {"simulation": result})
            return

        if parsed.path == "/api/research":
            composition = payload.get("composition") or {}
            custom_query = str(payload.get("query") or "")
            if not isinstance(composition, dict) or not composition:
                json_response(self, {"error": "Envie composition com material: fracao."}, status=400)
                return
            query = build_research_query(composition, custom_query)
            json_response(self, run_research_search(query))
            return

        json_response(self, {"error": "Rota nao encontrada."}, status=404)

    def serve_static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"

        requested = (STATIC_DIR / path.lstrip("/")).resolve()
        if not str(requested).startswith(str(STATIC_DIR.resolve())):
            self.send_error(403)
            return

        if not requested.exists() or not requested.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        body = requested.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Servidor rodando em http://{HOST}:{PORT}")
    print("Pressione Ctrl+C para parar.")
    server.serve_forever()


if __name__ == "__main__":
    main()
