"""
Simulador simples de materiais com catalogo local e API opcional.

O modelo faz uma triagem aproximada por regra de mistura. Ele e util para
prototipagem e pesquisa inicial, mas nao substitui ensaios de laboratorio,
DFT, CALPHAD, FEA ou dados cristalograficos validados.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Optional

try:
    import requests
except ImportError:
    requests = None


@dataclass(frozen=True)
class Material:
    name: str
    formula: str
    symbol: str
    category: str
    atomic_number: int
    atomic_mass_u: float
    density_g_cm3: float
    elastic_modulus_gpa: float
    thermal_conductivity_w_mk: float
    electrical_conductivity_s_m: float
    band_gap_ev: float
    melting_point_c: float
    atomic_radius_pm: float
    electronegativity: float
    crystal_structure: str
    color: str
    hardness_vickers_hv: float = 0.0
    source: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def m(
    name: str,
    formula: str,
    symbol: str,
    category: str,
    atomic_number: int,
    atomic_mass_u: float,
    density_g_cm3: float,
    elastic_modulus_gpa: float,
    thermal_conductivity_w_mk: float,
    electrical_conductivity_s_m: float,
    band_gap_ev: float,
    melting_point_c: float,
    atomic_radius_pm: float,
    electronegativity: float,
    crystal_structure: str,
    color: str,
    hardness_vickers_hv: Optional[float] = None,
) -> Material:
    if hardness_vickers_hv is None:
        hardness_vickers_hv = estimate_hardness_from_properties(
            category,
            elastic_modulus_gpa,
            melting_point_c,
        )
    return Material(
        name=name,
        formula=formula,
        symbol=symbol,
        category=category,
        atomic_number=atomic_number,
        atomic_mass_u=atomic_mass_u,
        density_g_cm3=density_g_cm3,
        elastic_modulus_gpa=elastic_modulus_gpa,
        thermal_conductivity_w_mk=thermal_conductivity_w_mk,
        electrical_conductivity_s_m=electrical_conductivity_s_m,
        band_gap_ev=band_gap_ev,
        melting_point_c=melting_point_c,
        atomic_radius_pm=atomic_radius_pm,
        electronegativity=electronegativity,
        crystal_structure=crystal_structure,
        color=color,
        hardness_vickers_hv=hardness_vickers_hv,
    )


def estimate_hardness_from_properties(
    category: str,
    elastic_modulus_gpa: float,
    melting_point_c: float,
) -> float:
    category = category.lower()
    if elastic_modulus_gpa <= 0:
        return 0.0
    factor = 2.0
    if "ceramico" in category or "carbeto" in category:
        factor = 7.0
    elif "nanomaterial" in category:
        factor = 5.0
    elif "semicondutor" in category:
        factor = 3.0
    elif "liga" in category:
        factor = 1.6
    elif "metal" in category:
        factor = 0.9
    thermal_bonus = 1.0 + max(0.0, min(melting_point_c, 2500.0)) / 10000.0
    return round(elastic_modulus_gpa * factor * thermal_bonus, 1)


LOCAL_MATERIALS: Dict[str, Material] = {
    "hidrogenio": m("Hidrogenio", "H", "H", "nao metal", 1, 1.008, 0.00009, 0, 0.18, 0, 0, -259.1, 53, 2.20, "molecular", "#7aa7ff"),
    "carbono": m("Carbono", "C", "C", "nao metal", 6, 12.011, 2.26, 10, 150, 2.0e4, 0, 3650, 70, 2.55, "hexagonal", "#2d2f33"),
    "grafeno": m("Grafeno", "C", "C", "nanomaterial", 6, 12.011, 2.20, 1000, 3000, 1.0e8, 0, 3650, 70, 2.55, "hexagonal 2D", "#202326"),
    "grafite": m("Grafite", "C", "C", "nao metal", 6, 12.011, 2.20, 10, 150, 1.0e5, 0, 3650, 70, 2.55, "hexagonal", "#34383d"),
    "magnesio": m("Magnesio", "Mg", "Mg", "metal alcalino-terroso", 12, 24.305, 1.74, 45, 160, 2.3e7, 0, 650, 145, 1.31, "hcp", "#9fb7c8"),
    "aluminio": m("Aluminio", "Al", "Al", "metal", 13, 26.982, 2.70, 69, 237, 3.77e7, 0, 660.3, 118, 1.61, "fcc", "#a8b7c7"),
    "silicio": m("Silicio", "Si", "Si", "metaloide", 14, 28.085, 2.33, 130, 149, 1.6e-3, 1.12, 1414, 111, 1.90, "diamante cubica", "#6f7f86"),
    "titanio": m("Titanio", "Ti", "Ti", "metal de transicao", 22, 47.867, 4.51, 116, 21.9, 2.4e6, 0, 1668, 147, 1.54, "hcp", "#9aa1aa"),
    "vanadio": m("Vanadio", "V", "V", "metal de transicao", 23, 50.942, 6.11, 128, 86, 5.0e6, 0, 1910, 134, 1.63, "bcc", "#8fa3ad"),
    "cromo": m("Cromo", "Cr", "Cr", "metal de transicao", 24, 51.996, 7.19, 279, 94, 7.9e6, 0, 1907, 128, 1.66, "bcc", "#8aa4bc"),
    "manganes": m("Manganes", "Mn", "Mn", "metal de transicao", 25, 54.938, 7.30, 198, 7.8, 6.2e5, 0, 1246, 127, 1.55, "cubica complexa", "#9b8f9d"),
    "ferro": m("Ferro", "Fe", "Fe", "metal de transicao", 26, 55.845, 7.87, 211, 80, 1.0e7, 0, 1538, 126, 1.83, "bcc", "#8d9496"),
    "cobalto": m("Cobalto", "Co", "Co", "metal de transicao", 27, 58.933, 8.90, 209, 63, 1.7e7, 0, 1495, 125, 1.88, "hcp", "#6f86aa"),
    "niquel": m("Niquel", "Ni", "Ni", "metal de transicao", 28, 58.693, 8.91, 200, 90, 1.43e7, 0, 1455, 124, 1.91, "fcc", "#a7a08a"),
    "cobre": m("Cobre", "Cu", "Cu", "metal de transicao", 29, 63.546, 8.96, 117, 401, 5.96e7, 0, 1084.6, 128, 1.90, "fcc", "#c56f37"),
    "zinco": m("Zinco", "Zn", "Zn", "metal de transicao", 30, 65.38, 7.14, 108, 116, 1.69e7, 0, 419.5, 134, 1.65, "hcp", "#9daab3"),
    "galio": m("Galio", "Ga", "Ga", "metal pos-transicao", 31, 69.723, 5.91, 9.8, 55, 7.1e6, 0, 29.8, 136, 1.81, "ortorrombica", "#8faeb7"),
    "germanio": m("Germanio", "Ge", "Ge", "metaloide", 32, 72.630, 5.32, 103, 60, 2.0, 0.67, 938.3, 122, 2.01, "diamante cubica", "#7f8c88"),
    "prata": m("Prata", "Ag", "Ag", "metal de transicao", 47, 107.868, 10.49, 83, 429, 6.30e7, 0, 961.8, 144, 1.93, "fcc", "#cfd6d8"),
    "estanho": m("Estanho", "Sn", "Sn", "metal pos-transicao", 50, 118.710, 7.31, 50, 67, 9.1e6, 0, 231.9, 140, 1.96, "tetragonal", "#aeb9bd"),
    "tungstenio": m("Tungstenio", "W", "W", "metal de transicao", 74, 183.84, 19.25, 411, 134, 1.79e7, 0, 3422, 139, 2.36, "bcc", "#78848a"),
    "ouro": m("Ouro", "Au", "Au", "metal de transicao", 79, 196.967, 19.32, 78, 317, 4.10e7, 0, 1064.2, 144, 2.54, "fcc", "#d6a83a"),
    "mercurio": m("Mercurio", "Hg", "Hg", "metal de transicao", 80, 200.592, 13.53, 0, 2, 1.0e6, 0, -38.8, 151, 2.00, "liquido", "#9aa6b2"),
    "chumbo": m("Chumbo", "Pb", "Pb", "metal pos-transicao", 82, 207.2, 11.34, 16, 35, 4.8e6, 0, 327.5, 175, 2.33, "fcc", "#6d7583"),
    "fosforo_negro": m("Fosforo negro", "P", "P", "semicondutor 2D", 15, 30.974, 2.69, 44, 12, 1.0e2, 0.3, 590, 98, 2.19, "ortorrombica em camadas", "#2b2630"),
    "bismuto": m("Bismuto", "Bi", "Bi", "metal pos-transicao", 83, 208.980, 9.78, 32, 7.97, 7.7e5, 0, 271.4, 156, 2.02, "romboedrica", "#b7a5ba"),
    "tecnecio": m("Tecnecio", "Tc", "Tc", "metal de transicao", 43, 98.0, 11.50, 290, 50.6, 6.7e6, 0, 2157, 136, 1.90, "hcp", "#8d95a6"),
    "telureto_bismuto": m("Telureto de bismuto", "Bi2Te3", "Bi2Te3", "semicondutor termoeletrico", 0, 800.76, 7.86, 44, 1.5, 1.0e5, 0.15, 585, 160, 2.10, "romboedrica em camadas", "#7d718d"),
    "telureto_chumbo": m("Telureto de chumbo", "PbTe", "PbTe", "semicondutor termoeletrico", 0, 334.8, 8.16, 57, 2.3, 2.0e4, 0.31, 924, 170, 2.25, "sal-gema fcc", "#59656f"),
    "telureto_cadmio": m("Telureto de cadmio", "CdTe", "CdTe", "semicondutor", 0, 240.0, 5.85, 52, 6.2, 1.0e-2, 1.50, 1092, 155, 2.10, "zinc blende", "#6b4f63"),
    "telureto_estanho": m("Telureto de estanho", "SnTe", "SnTe", "semicondutor topologico", 0, 246.3, 6.48, 50, 8.0, 1.0e5, 0.18, 806, 155, 2.10, "sal-gema fcc", "#6f7780"),
    "seleneto_estanho": m("Seleneto de estanho", "SnSe", "SnSe", "semicondutor termoeletrico", 0, 197.67, 6.18, 38, 0.7, 1.0e3, 0.90, 861, 145, 2.25, "ortorrombica em camadas", "#5f6672"),
    "selenato_estanho": m("Selenato de estanho", "SnSeO4", "SnSeO4", "sal inorganico", 0, 261.68, 4.20, 45, 1.2, 1.0e-8, 3.20, 520, 145, 2.40, "cristal ionico estimado", "#7f8c9a"),
    "seleneto_estanho_2": m("Disseleneto de estanho", "SnSe2", "SnSe2", "semicondutor 2D", 0, 276.63, 5.90, 35, 1.0, 5.0e1, 1.00, 861, 150, 2.35, "CdI2 hexagonal em camadas", "#4f6678"),
    "sulfeto_molibdenio": m("Dissulfeto de molibdenio", "MoS2", "MoS2", "semicondutor 2D", 0, 160.07, 5.06, 270, 85, 1.0e-3, 1.80, 1185, 145, 2.25, "hexagonal em camadas", "#394b59"),
    "sulfeto_tungstenio": m("Dissulfeto de tungstenio", "WS2", "WS2", "semicondutor 2D", 0, 247.97, 7.50, 170, 32, 1.0e-3, 2.00, 1250, 150, 2.30, "hexagonal em camadas", "#4d5661"),
    "nitreto_boro": m("Nitreto de boro hexagonal", "h-BN", "BN", "ceramico 2D", 0, 24.82, 2.10, 800, 400, 1.0e-12, 5.90, 2973, 82, 2.50, "hexagonal em camadas", "#e8eef0"),
    "oxido_estanho": m("Oxido de estanho", "SnO2", "SnO2", "oxido semicondutor", 0, 150.71, 6.95, 250, 98, 1.0e2, 3.60, 1630, 140, 2.20, "rutilo tetragonal", "#d4dae1"),
    "oxido_zinco": m("Oxido de zinco", "ZnO", "ZnO", "oxido semicondutor", 0, 81.38, 5.61, 140, 50, 1.0e-2, 3.30, 1975, 134, 2.00, "wurtzita", "#d6dbe0"),
    "dioxido_titanio": m("Dioxido de titanio", "TiO2", "TiO2", "ceramico semicondutor", 0, 79.87, 4.23, 230, 8.5, 1.0e-12, 3.20, 1843, 147, 2.20, "rutilo/anatase", "#e3e6e8"),
    "arseneto_galio": m("Arseneto de galio", "GaAs", "GaAs", "semicondutor III-V", 0, 144.64, 5.32, 85, 46, 1.0e-6, 1.42, 1238, 130, 2.00, "zinc blende", "#766f82"),
    "fosfeto_indio": m("Fosfeto de indio", "InP", "InP", "semicondutor III-V", 0, 145.79, 4.81, 71, 68, 1.0e-5, 1.34, 1062, 140, 1.95, "zinc blende", "#7f7584"),
    "latao": m("Latao", "Cu-Zn", "CuZn", "liga", 0, 0, 8.50, 100, 120, 1.6e7, 0, 930, 130, 1.80, "fcc/beta bcc", "#c99a4a"),
    "bronze": m("Bronze", "Cu-Sn", "CuSn", "liga", 0, 0, 8.80, 110, 60, 7.0e6, 0, 950, 135, 1.85, "fcc/intermetalicos", "#a66b3d"),
    "aco_inoxidavel_304": m("Aco inoxidavel 304", "Fe-Cr-Ni", "SS304", "liga", 0, 0, 8.00, 193, 16, 1.4e6, 0, 1400, 126, 1.85, "austenitica fcc", "#9aa0a3"),
    "inconel_718": m("Inconel 718", "Ni-Cr-Fe-Nb", "IN718", "superliga", 0, 0, 8.19, 200, 11.4, 8.0e5, 0, 1336, 130, 1.90, "gamma fcc + precipitados", "#8f9290"),
    "solda_sn_pb": m("Solda estanho-chumbo", "Sn63Pb37", "SnPb", "liga", 0, 0, 8.40, 32, 50, 7.0e6, 0, 183, 155, 2.10, "eutetica tetragonal/fcc", "#9b9da3"),
    "abs": m("ABS", "(C8H8-C4H6-C3H3N)n", "ABS", "polimero", 0, 0, 1.05, 2.2, 0.18, 1.0e-14, 5.0, 105, 80, 2.50, "amorfa", "#d8d2c7"),
    "pla": m("PLA", "(C3H4O2)n", "PLA", "polimero", 0, 0, 1.24, 3.5, 0.13, 1.0e-14, 5.0, 160, 80, 2.60, "semicristalina", "#e7dfcf"),
    "pet": m("PET", "(C10H8O4)n", "PET", "polimero", 0, 0, 1.38, 2.8, 0.24, 1.0e-14, 5.0, 260, 85, 2.60, "semicristalina", "#dce8ec"),
    "peek": m("PEEK", "(C19H12O3)n", "PEEK", "polimero engenharia", 0, 0, 1.30, 3.6, 0.25, 1.0e-14, 5.0, 343, 85, 2.60, "semicristalina", "#c8b895"),
    "ptfe": m("PTFE", "(C2F4)n", "PTFE", "polimero fluorinado", 0, 0, 2.20, 0.5, 0.25, 1.0e-18, 5.8, 327, 90, 3.00, "semicristalina", "#f1f4f4"),
    "poliimida": m("Poliimida", "PI", "PI", "polimero alta temperatura", 0, 0, 1.42, 2.5, 0.12, 1.0e-15, 5.2, 400, 85, 2.60, "amorfa", "#b87b43"),
    "aco": m("Aco carbono", "Fe-C", "Fe", "liga", 0, 0, 7.85, 200, 50, 6.0e6, 0, 1425, 126, 1.83, "bcc/fcc", "#747c80"),
    "vidro": m("Vidro sodocalcico", "SiO2-Na2O-CaO", "Si", "ceramico", 0, 0, 2.50, 70, 0.84, 1.0e-12, 8.0, 1500, 111, 1.90, "amorfa", "#86c9d7"),
    "alumina": m("Alumina", "Al2O3", "Al", "ceramico", 0, 0, 3.95, 300, 30, 1.0e-12, 8.8, 2072, 118, 1.61, "corindon", "#dfe6ec"),
    "carbeto_silicio": m("Carbeto de silicio", "SiC", "Si", "ceramico", 0, 0, 3.21, 410, 120, 1.0e-6, 2.9, 2730, 111, 1.90, "zinc blende/hexagonal", "#5b676b"),
}


def estimate_element_properties(
    category: str,
    density_g_cm3: float,
    melting_point_c: float,
) -> dict[str, float | str]:
    category = category.lower()

    if "gas nobre" in category:
        return {
            "elastic_modulus_gpa": 0.0,
            "thermal_conductivity_w_mk": 0.02,
            "electrical_conductivity_s_m": 0.0,
            "band_gap_ev": 10.0,
            "crystal_structure": "gas monoatomico",
            "color": "#7aa7ff",
        }
    if "halogenio" in category:
        return {
            "elastic_modulus_gpa": 1.0,
            "thermal_conductivity_w_mk": 0.05,
            "electrical_conductivity_s_m": 1.0e-12,
            "band_gap_ev": 4.0,
            "crystal_structure": "molecular",
            "color": "#87b66b",
        }
    if "nao metal" in category:
        return {
            "elastic_modulus_gpa": 8.0,
            "thermal_conductivity_w_mk": 0.3,
            "electrical_conductivity_s_m": 1.0e-8,
            "band_gap_ev": 4.0,
            "crystal_structure": "molecular/covalente",
            "color": "#7aa7ff",
        }
    if "metaloide" in category:
        return {
            "elastic_modulus_gpa": 70.0,
            "thermal_conductivity_w_mk": 35.0,
            "electrical_conductivity_s_m": 1.0,
            "band_gap_ev": 1.2,
            "crystal_structure": "covalente",
            "color": "#6f7f86",
        }
    if "alcalino-terroso" in category:
        return {
            "elastic_modulus_gpa": 35.0,
            "thermal_conductivity_w_mk": 90.0,
            "electrical_conductivity_s_m": 1.0e7,
            "band_gap_ev": 0.0,
            "crystal_structure": "hcp/fcc",
            "color": "#aeb9bd",
        }
    if "alcalino" in category:
        return {
            "elastic_modulus_gpa": 8.0,
            "thermal_conductivity_w_mk": 60.0,
            "electrical_conductivity_s_m": 8.0e6,
            "band_gap_ev": 0.0,
            "crystal_structure": "bcc",
            "color": "#b8b4a6",
        }
    if "lantanideo" in category:
        return {
            "elastic_modulus_gpa": 45.0,
            "thermal_conductivity_w_mk": 12.0,
            "electrical_conductivity_s_m": 1.5e6,
            "band_gap_ev": 0.0,
            "crystal_structure": "hcp/fcc",
            "color": "#9fb2b5",
        }
    if "actinideo" in category:
        return {
            "elastic_modulus_gpa": 70.0,
            "thermal_conductivity_w_mk": 18.0,
            "electrical_conductivity_s_m": 1.0e6,
            "band_gap_ev": 0.0,
            "crystal_structure": "complexa",
            "color": "#8c9a8f",
        }
    if "pos-transicao" in category:
        return {
            "elastic_modulus_gpa": 35.0,
            "thermal_conductivity_w_mk": 30.0,
            "electrical_conductivity_s_m": 4.0e6,
            "band_gap_ev": 0.0,
            "crystal_structure": "metalica",
            "color": "#aeb9bd",
        }

    return {
        "elastic_modulus_gpa": 120.0 if density_g_cm3 > 0 else 0.0,
        "thermal_conductivity_w_mk": 45.0 if density_g_cm3 > 0 else 0.0,
        "electrical_conductivity_s_m": 7.0e6 if density_g_cm3 > 0 else 0.0,
        "band_gap_ev": 0.0,
        "crystal_structure": "metalica",
        "color": "#8fa3ad",
    }


PERIODIC_TABLE_BASE = [
    ("hidrogenio", "Hidrogenio", "H", 1, 1.008, "nao metal", 0.00009, -259.1, 53, 2.20),
    ("helio", "Helio", "He", 2, 4.0026, "gas nobre", 0.00018, -272.2, 31, 0.0),
    ("litio", "Litio", "Li", 3, 6.94, "metal alcalino", 0.534, 180.5, 167, 0.98),
    ("berilio", "Berilio", "Be", 4, 9.0122, "metal alcalino-terroso", 1.85, 1287, 112, 1.57),
    ("boro", "Boro", "B", 5, 10.81, "metaloide", 2.34, 2076, 87, 2.04),
    ("carbono", "Carbono", "C", 6, 12.011, "nao metal", 2.26, 3650, 70, 2.55),
    ("nitrogenio", "Nitrogenio", "N", 7, 14.007, "nao metal", 0.00125, -210.0, 56, 3.04),
    ("oxigenio", "Oxigenio", "O", 8, 15.999, "nao metal", 0.00143, -218.8, 48, 3.44),
    ("fluor", "Fluor", "F", 9, 18.998, "halogenio", 0.00170, -219.7, 42, 3.98),
    ("neon", "Neon", "Ne", 10, 20.180, "gas nobre", 0.00090, -248.6, 38, 0.0),
    ("sodio", "Sodio", "Na", 11, 22.990, "metal alcalino", 0.97, 97.8, 190, 0.93),
    ("magnesio", "Magnesio", "Mg", 12, 24.305, "metal alcalino-terroso", 1.74, 650, 145, 1.31),
    ("aluminio", "Aluminio", "Al", 13, 26.982, "metal pos-transicao", 2.70, 660.3, 118, 1.61),
    ("silicio", "Silicio", "Si", 14, 28.085, "metaloide", 2.33, 1414, 111, 1.90),
    ("fosforo", "Fosforo", "P", 15, 30.974, "nao metal", 1.82, 44.1, 98, 2.19),
    ("enxofre", "Enxofre", "S", 16, 32.06, "nao metal", 2.07, 115.2, 88, 2.58),
    ("cloro", "Cloro", "Cl", 17, 35.45, "halogenio", 0.0032, -101.5, 79, 3.16),
    ("argon", "Argon", "Ar", 18, 39.948, "gas nobre", 0.00178, -189.3, 71, 0.0),
    ("potassio", "Potassio", "K", 19, 39.098, "metal alcalino", 0.86, 63.4, 243, 0.82),
    ("calcio", "Calcio", "Ca", 20, 40.078, "metal alcalino-terroso", 1.54, 842, 194, 1.00),
    ("escandio", "Escandio", "Sc", 21, 44.956, "metal de transicao", 2.99, 1541, 184, 1.36),
    ("titanio", "Titanio", "Ti", 22, 47.867, "metal de transicao", 4.51, 1668, 147, 1.54),
    ("vanadio", "Vanadio", "V", 23, 50.942, "metal de transicao", 6.11, 1910, 134, 1.63),
    ("cromo", "Cromo", "Cr", 24, 51.996, "metal de transicao", 7.19, 1907, 128, 1.66),
    ("manganes", "Manganes", "Mn", 25, 54.938, "metal de transicao", 7.30, 1246, 127, 1.55),
    ("ferro", "Ferro", "Fe", 26, 55.845, "metal de transicao", 7.87, 1538, 126, 1.83),
    ("cobalto", "Cobalto", "Co", 27, 58.933, "metal de transicao", 8.90, 1495, 125, 1.88),
    ("niquel", "Niquel", "Ni", 28, 58.693, "metal de transicao", 8.91, 1455, 124, 1.91),
    ("cobre", "Cobre", "Cu", 29, 63.546, "metal de transicao", 8.96, 1084.6, 128, 1.90),
    ("zinco", "Zinco", "Zn", 30, 65.38, "metal de transicao", 7.14, 419.5, 134, 1.65),
    ("galio", "Galio", "Ga", 31, 69.723, "metal pos-transicao", 5.91, 29.8, 136, 1.81),
    ("germanio", "Germanio", "Ge", 32, 72.630, "metaloide", 5.32, 938.3, 122, 2.01),
    ("arsenio", "Arsenio", "As", 33, 74.922, "metaloide", 5.73, 816.8, 119, 2.18),
    ("selenio", "Selenio", "Se", 34, 78.971, "nao metal", 4.81, 221, 120, 2.55),
    ("bromo", "Bromo", "Br", 35, 79.904, "halogenio", 3.11, -7.2, 120, 2.96),
    ("cripton", "Cripton", "Kr", 36, 83.798, "gas nobre", 0.0037, -157.4, 88, 3.00),
    ("rubidio", "Rubidio", "Rb", 37, 85.468, "metal alcalino", 1.53, 39.3, 265, 0.82),
    ("estroncio", "Estroncio", "Sr", 38, 87.62, "metal alcalino-terroso", 2.64, 777, 219, 0.95),
    ("itrio", "Itrio", "Y", 39, 88.906, "metal de transicao", 4.47, 1526, 212, 1.22),
    ("zirconio", "Zirconio", "Zr", 40, 91.224, "metal de transicao", 6.52, 1855, 206, 1.33),
    ("niobio", "Niobio", "Nb", 41, 92.906, "metal de transicao", 8.57, 2477, 198, 1.60),
    ("molibdenio", "Molibdenio", "Mo", 42, 95.95, "metal de transicao", 10.28, 2623, 190, 2.16),
    ("tecnecio", "Tecnecio", "Tc", 43, 98.0, "metal de transicao", 11.50, 2157, 136, 1.90),
    ("rutenio", "Rutenio", "Ru", 44, 101.07, "metal de transicao", 12.37, 2334, 178, 2.20),
    ("rodio", "Rodio", "Rh", 45, 102.91, "metal de transicao", 12.41, 1964, 173, 2.28),
    ("paladio", "Paladio", "Pd", 46, 106.42, "metal de transicao", 12.02, 1554.9, 169, 2.20),
    ("prata", "Prata", "Ag", 47, 107.868, "metal de transicao", 10.49, 961.8, 144, 1.93),
    ("cadmio", "Cadmio", "Cd", 48, 112.414, "metal de transicao", 8.65, 321.1, 151, 1.69),
    ("indio", "Indio", "In", 49, 114.818, "metal pos-transicao", 7.31, 156.6, 167, 1.78),
    ("estanho", "Estanho", "Sn", 50, 118.710, "metal pos-transicao", 7.31, 231.9, 140, 1.96),
    ("antimonio", "Antimonio", "Sb", 51, 121.760, "metaloide", 6.69, 630.6, 139, 2.05),
    ("telurio", "Telurio", "Te", 52, 127.60, "metaloide", 6.24, 449.5, 138, 2.10),
    ("iodo", "Iodo", "I", 53, 126.904, "halogenio", 4.93, 113.7, 139, 2.66),
    ("xenon", "Xenon", "Xe", 54, 131.293, "gas nobre", 0.0059, -111.8, 108, 2.60),
    ("cesio", "Cesio", "Cs", 55, 132.905, "metal alcalino", 1.93, 28.5, 298, 0.79),
    ("bario", "Bario", "Ba", 56, 137.327, "metal alcalino-terroso", 3.62, 727, 253, 0.89),
    ("lantanio", "Lantanio", "La", 57, 138.905, "lantanideo", 6.15, 920, 195, 1.10),
    ("cerio", "Cerio", "Ce", 58, 140.116, "lantanideo", 6.77, 798, 185, 1.12),
    ("praseodimio", "Praseodimio", "Pr", 59, 140.908, "lantanideo", 6.77, 931, 185, 1.13),
    ("neodimio", "Neodimio", "Nd", 60, 144.242, "lantanideo", 7.01, 1021, 185, 1.14),
    ("promecio", "Promecio", "Pm", 61, 145.0, "lantanideo", 7.26, 1042, 185, 1.13),
    ("samario", "Samario", "Sm", 62, 150.36, "lantanideo", 7.52, 1072, 185, 1.17),
    ("europio", "Europio", "Eu", 63, 151.964, "lantanideo", 5.24, 826, 185, 1.20),
    ("gadolinio", "Gadolinio", "Gd", 64, 157.25, "lantanideo", 7.90, 1313, 180, 1.20),
    ("terbio", "Terbio", "Tb", 65, 158.925, "lantanideo", 8.23, 1356, 175, 1.10),
    ("disprosio", "Disprosio", "Dy", 66, 162.500, "lantanideo", 8.55, 1412, 175, 1.22),
    ("holmio", "Holmio", "Ho", 67, 164.930, "lantanideo", 8.80, 1474, 175, 1.23),
    ("erbio", "Erbio", "Er", 68, 167.259, "lantanideo", 9.07, 1529, 175, 1.24),
    ("tulio", "Tulio", "Tm", 69, 168.934, "lantanideo", 9.32, 1545, 175, 1.25),
    ("iterbio", "Iterbio", "Yb", 70, 173.045, "lantanideo", 6.90, 824, 175, 1.10),
    ("lutecio", "Lutecio", "Lu", 71, 174.967, "lantanideo", 9.84, 1663, 175, 1.27),
    ("hafnio", "Hafnio", "Hf", 72, 178.49, "metal de transicao", 13.31, 2233, 208, 1.30),
    ("tantalo", "Tantalo", "Ta", 73, 180.948, "metal de transicao", 16.69, 3017, 200, 1.50),
    ("tungstenio", "Tungstenio", "W", 74, 183.84, "metal de transicao", 19.25, 3422, 139, 2.36),
    ("renio", "Renio", "Re", 75, 186.207, "metal de transicao", 21.02, 3186, 188, 1.90),
    ("osmio", "Osmio", "Os", 76, 190.23, "metal de transicao", 22.59, 3033, 185, 2.20),
    ("iridio", "Iridio", "Ir", 77, 192.217, "metal de transicao", 22.56, 2446, 180, 2.20),
    ("platina", "Platina", "Pt", 78, 195.084, "metal de transicao", 21.45, 1768.3, 177, 2.28),
    ("ouro", "Ouro", "Au", 79, 196.967, "metal de transicao", 19.32, 1064.2, 144, 2.54),
    ("mercurio", "Mercurio", "Hg", 80, 200.592, "metal de transicao", 13.53, -38.8, 151, 2.00),
    ("talio", "Talio", "Tl", 81, 204.38, "metal pos-transicao", 11.85, 304, 170, 1.62),
    ("chumbo", "Chumbo", "Pb", 82, 207.2, "metal pos-transicao", 11.34, 327.5, 175, 2.33),
    ("bismuto", "Bismuto", "Bi", 83, 208.980, "metal pos-transicao", 9.78, 271.4, 156, 2.02),
    ("polonio", "Polonio", "Po", 84, 209.0, "metaloide", 9.20, 254, 168, 2.00),
    ("astato", "Astato", "At", 85, 210.0, "halogenio", 7.00, 302, 150, 2.20),
    ("radonio", "Radonio", "Rn", 86, 222.0, "gas nobre", 0.0097, -71, 120, 0.0),
    ("francio", "Francio", "Fr", 87, 223.0, "metal alcalino", 1.87, 27, 348, 0.70),
    ("radio", "Radio", "Ra", 88, 226.0, "metal alcalino-terroso", 5.50, 700, 283, 0.90),
    ("actinio", "Actinio", "Ac", 89, 227.0, "actinideo", 10.07, 1050, 195, 1.10),
    ("torio", "Torio", "Th", 90, 232.038, "actinideo", 11.72, 1750, 180, 1.30),
    ("protactinio", "Protactinio", "Pa", 91, 231.036, "actinideo", 15.37, 1572, 180, 1.50),
    ("uranio", "Uranio", "U", 92, 238.029, "actinideo", 19.05, 1132, 175, 1.38),
    ("netunio", "Netunio", "Np", 93, 237.0, "actinideo", 20.45, 644, 175, 1.36),
    ("plutonio", "Plutonio", "Pu", 94, 244.0, "actinideo", 19.84, 640, 175, 1.28),
    ("americio", "Americio", "Am", 95, 243.0, "actinideo", 13.67, 1176, 175, 1.30),
    ("curio", "Curio", "Cm", 96, 247.0, "actinideo", 13.51, 1345, 175, 1.30),
    ("berquelio", "Berquelio", "Bk", 97, 247.0, "actinideo", 14.78, 986, 170, 1.30),
    ("californio", "Californio", "Cf", 98, 251.0, "actinideo", 15.10, 900, 170, 1.30),
    ("einstenio", "Einstenio", "Es", 99, 252.0, "actinideo", 8.84, 860, 170, 1.30),
    ("fermio", "Fermio", "Fm", 100, 257.0, "actinideo", 9.70, 1527, 170, 1.30),
    ("mendelevio", "Mendelevio", "Md", 101, 258.0, "actinideo", 10.30, 827, 170, 1.30),
    ("nobelio", "Nobelio", "No", 102, 259.0, "actinideo", 9.90, 827, 170, 1.30),
    ("lawrencio", "Lawrencio", "Lr", 103, 266.0, "actinideo", 15.60, 1627, 170, 1.30),
    ("rutherfordio", "Rutherfordio", "Rf", 104, 267.0, "metal de transicao sintetico", 17.0, 2100, 170, 0.0),
    ("dubnio", "Dubnio", "Db", 105, 268.0, "metal de transicao sintetico", 21.6, 0, 170, 0.0),
    ("seaborgio", "Seaborgio", "Sg", 106, 269.0, "metal de transicao sintetico", 23.0, 0, 170, 0.0),
    ("bohrio", "Bohrio", "Bh", 107, 270.0, "metal de transicao sintetico", 26.0, 0, 170, 0.0),
    ("hassio", "Hassio", "Hs", 108, 277.0, "metal de transicao sintetico", 27.0, 0, 170, 0.0),
    ("meitnerio", "Meitnerio", "Mt", 109, 278.0, "metal de transicao sintetico", 28.0, 0, 170, 0.0),
    ("darmstadtio", "Darmstadtio", "Ds", 110, 281.0, "metal de transicao sintetico", 29.0, 0, 170, 0.0),
    ("roentgenio", "Roentgenio", "Rg", 111, 282.0, "metal de transicao sintetico", 28.7, 0, 170, 0.0),
    ("copernicio", "Copernicio", "Cn", 112, 285.0, "metal de transicao sintetico", 14.0, 0, 170, 0.0),
    ("nihonio", "Nihonio", "Nh", 113, 286.0, "metal pos-transicao sintetico", 16.0, 0, 170, 0.0),
    ("flerovio", "Flerovio", "Fl", 114, 289.0, "metal pos-transicao sintetico", 14.0, 0, 170, 0.0),
    ("moscovio", "Moscovio", "Mc", 115, 290.0, "metal pos-transicao sintetico", 13.5, 0, 170, 0.0),
    ("livermorio", "Livermorio", "Lv", 116, 293.0, "metal pos-transicao sintetico", 12.9, 0, 170, 0.0),
    ("tenesso", "Tenesso", "Ts", 117, 294.0, "halogenio sintetico", 7.2, 0, 170, 0.0),
    ("oganessonio", "Oganessonio", "Og", 118, 294.0, "gas nobre sintetico", 7.0, 0, 170, 0.0),
]


def add_periodic_table_elements() -> None:
    for (
        key,
        name,
        symbol,
        atomic_number,
        atomic_mass_u,
        category,
        density_g_cm3,
        melting_point_c,
        atomic_radius_pm,
        electronegativity,
    ) in PERIODIC_TABLE_BASE:
        if key in LOCAL_MATERIALS:
            continue

        props = estimate_element_properties(category, density_g_cm3, melting_point_c)
        LOCAL_MATERIALS[key] = m(
            name=name,
            formula=symbol,
            symbol=symbol,
            category=category,
            atomic_number=atomic_number,
            atomic_mass_u=atomic_mass_u,
            density_g_cm3=density_g_cm3,
            elastic_modulus_gpa=float(props["elastic_modulus_gpa"]),
            thermal_conductivity_w_mk=float(props["thermal_conductivity_w_mk"]),
            electrical_conductivity_s_m=float(props["electrical_conductivity_s_m"]),
            band_gap_ev=float(props["band_gap_ev"]),
            melting_point_c=melting_point_c,
            atomic_radius_pm=atomic_radius_pm,
            electronegativity=electronegativity,
            crystal_structure=str(props["crystal_structure"]),
            color=str(props["color"]),
        )


add_periodic_table_elements()


RARE_EARTH_COMPOUNDS = [
    ("oxido_escandio", "Oxido de escandio", "Sc2O3", "Sc2O3", 137.91, 3.86, 200, 12, 1.0e-12, 5.7, 2485, 184, 1.36, "bixbyita cubica", "#d8e0df"),
    ("oxido_itrio", "Oxido de itrio", "Y2O3", "Y2O3", 225.81, 5.01, 180, 13, 1.0e-12, 5.5, 2430, 212, 1.22, "bixbyita cubica", "#dce5e0"),
    ("oxido_lantanio", "Oxido de lantanio", "La2O3", "La2O3", 325.81, 6.51, 150, 10, 1.0e-12, 4.3, 2315, 195, 1.10, "hexagonal/cubica", "#d6ded8"),
    ("oxido_cerio", "Oxido de cerio", "CeO2", "CeO2", 172.11, 7.22, 230, 12, 1.0e-8, 3.2, 2400, 185, 1.12, "fluorita cubica", "#e2d48b"),
    ("oxido_praseodimio", "Oxido de praseodimio", "Pr6O11", "Pr6O11", 1021.44, 6.88, 160, 7, 1.0e-8, 2.1, 2183, 185, 1.13, "cubica complexa", "#6f7d4f"),
    ("oxido_neodimio", "Oxido de neodimio", "Nd2O3", "Nd2O3", 336.48, 7.24, 155, 10, 1.0e-11, 4.7, 2233, 185, 1.14, "hexagonal/cubica", "#a893c8"),
    ("oxido_promecio", "Oxido de promecio", "Pm2O3", "Pm2O3", 338.0, 6.60, 145, 8, 1.0e-11, 4.0, 2130, 185, 1.13, "cubica estimada", "#9aa4b5"),
    ("oxido_samario", "Oxido de samario", "Sm2O3", "Sm2O3", 348.72, 8.35, 150, 11, 1.0e-11, 4.3, 2335, 185, 1.17, "monoclinica/cubica", "#d4c0aa"),
    ("oxido_europio", "Oxido de europio", "Eu2O3", "Eu2O3", 351.93, 7.42, 145, 8, 1.0e-11, 4.4, 2350, 185, 1.20, "bixbyita cubica", "#d28fa1"),
    ("oxido_gadolinio", "Oxido de gadolinio", "Gd2O3", "Gd2O3", 362.50, 7.41, 160, 11, 1.0e-11, 5.3, 2420, 180, 1.20, "bixbyita cubica", "#bfc9b4"),
    ("oxido_terbio", "Oxido de terbio", "Tb4O7", "Tb4O7", 747.70, 7.30, 155, 9, 1.0e-9, 2.8, 2340, 175, 1.10, "fluorita/defeitos", "#6f7f5f"),
    ("oxido_disprosio", "Oxido de disprosio", "Dy2O3", "Dy2O3", 373.00, 7.81, 150, 10, 1.0e-11, 4.9, 2340, 175, 1.22, "bixbyita cubica", "#c9d5c7"),
    ("oxido_holmio", "Oxido de holmio", "Ho2O3", "Ho2O3", 377.86, 8.41, 150, 9, 1.0e-11, 5.3, 2415, 175, 1.23, "bixbyita cubica", "#e0c8b0"),
    ("oxido_erbio", "Oxido de erbio", "Er2O3", "Er2O3", 382.52, 8.64, 155, 12, 1.0e-11, 5.2, 2400, 175, 1.24, "bixbyita cubica", "#f0a2bf"),
    ("oxido_tulio", "Oxido de tulio", "Tm2O3", "Tm2O3", 385.87, 8.60, 150, 10, 1.0e-11, 5.0, 2425, 175, 1.25, "bixbyita cubica", "#b7c2d1"),
    ("oxido_iterbio", "Oxido de iterbio", "Yb2O3", "Yb2O3", 394.08, 9.17, 145, 9, 1.0e-11, 4.9, 2355, 175, 1.10, "bixbyita cubica", "#c6b6d2"),
    ("oxido_lutecio", "Oxido de lutecio", "Lu2O3", "Lu2O3", 397.93, 9.42, 170, 12, 1.0e-11, 5.5, 2490, 175, 1.27, "bixbyita cubica", "#cbd2ce"),
    ("iman_ndfeb", "Ima de neodimio ferro boro", "Nd2Fe14B", "NdFeB", 1081.1, 7.50, 160, 8, 6.0e5, 0.0, 1180, 160, 1.45, "tetragonal", "#7b6fa6"),
    ("iman_smco", "Ima de samario cobalto", "SmCo5", "SmCo", 445.0, 8.30, 150, 12, 1.0e6, 0.0, 1320, 160, 1.55, "hexagonal", "#8d7780"),
]


def add_rare_earth_compounds() -> None:
    for (
        key,
        name,
        formula,
        symbol,
        atomic_mass_u,
        density_g_cm3,
        elastic_modulus_gpa,
        thermal_conductivity_w_mk,
        electrical_conductivity_s_m,
        band_gap_ev,
        melting_point_c,
        atomic_radius_pm,
        electronegativity,
        crystal_structure,
        color,
    ) in RARE_EARTH_COMPOUNDS:
        if key in LOCAL_MATERIALS:
            continue
        LOCAL_MATERIALS[key] = m(
            name=name,
            formula=formula,
            symbol=symbol,
            category="composto de terra rara",
            atomic_number=0,
            atomic_mass_u=atomic_mass_u,
            density_g_cm3=density_g_cm3,
            elastic_modulus_gpa=elastic_modulus_gpa,
            thermal_conductivity_w_mk=thermal_conductivity_w_mk,
            electrical_conductivity_s_m=electrical_conductivity_s_m,
            band_gap_ev=band_gap_ev,
            melting_point_c=melting_point_c,
            atomic_radius_pm=atomic_radius_pm,
            electronegativity=electronegativity,
            crystal_structure=crystal_structure,
            color=color,
        )


add_rare_earth_compounds()


ADVANCED_READY_MATERIALS = [
    ("titanato_estroncio", "Titanato de estroncio", "SrTiO3", "SrTiO3", "perovskita oxida", 0, 183.49, 5.12, 280, 12, 1.0e-8, 3.25, 2080, 170, 1.70, "perovskita cubica", "#c8d5da"),
    ("titanato_bario", "Titanato de bario", "BaTiO3", "BaTiO3", "perovskita ferroeletrica", 0, 233.19, 6.02, 120, 6, 1.0e-10, 3.20, 1625, 180, 1.60, "perovskita tetragonal", "#d8d6c7"),
    ("titanato_chumbo", "Titanato de chumbo", "PbTiO3", "PbTiO3", "perovskita ferroeletrica", 0, 303.06, 7.52, 90, 3, 1.0e-10, 3.40, 1285, 175, 1.80, "perovskita tetragonal", "#b7bcc5"),
    ("titanato_calcio", "Titanato de calcio", "CaTiO3", "CaTiO3", "perovskita oxida", 0, 135.94, 4.04, 180, 6, 1.0e-12, 3.50, 1975, 165, 1.65, "perovskita ortorrombica", "#cfd6d4"),
    ("aluminato_lantanio", "Aluminato de lantanio", "LaAlO3", "LaAlO3", "perovskita oxida", 0, 213.89, 6.52, 190, 12, 1.0e-12, 5.60, 2080, 160, 1.50, "perovskita romboedrica", "#d7d2c3"),
    ("manganita_lantanio_estroncio", "Manganita de lantanio estroncio", "La0.7Sr0.3MnO3", "LSMO", "perovskita magnetorresistiva", 0, 0, 6.30, 150, 2.5, 1.0e5, 0.0, 1400, 160, 1.65, "perovskita romboedrica", "#5e4f5f"),
    ("mapbi3", "Perovskita MAPbI3", "CH3NH3PbI3", "MAPbI3", "perovskita halogenada", 0, 619.98, 4.16, 18, 0.5, 1.0e-4, 1.55, 330, 170, 2.30, "perovskita tetragonal", "#56465c"),
    ("fapbi3", "Perovskita FAPbI3", "HC(NH2)2PbI3", "FAPbI3", "perovskita halogenada", 0, 632.0, 4.10, 16, 0.5, 1.0e-4, 1.48, 330, 170, 2.30, "perovskita trigonal/cubica", "#5a465b"),
    ("cspbi3", "Perovskita CsPbI3", "CsPbI3", "CsPbI3", "perovskita halogenada", 0, 720.82, 5.39, 20, 0.4, 1.0e-5, 1.73, 460, 175, 2.25, "perovskita ortorrombica", "#5b4c3c"),
    ("cspbbr3", "Perovskita CsPbBr3", "CsPbBr3", "CsPbBr3", "perovskita halogenada", 0, 579.82, 4.83, 20, 0.5, 1.0e-6, 2.30, 567, 170, 2.30, "perovskita ortorrombica", "#687c42"),
    ("magnetita", "Magnetita", "Fe3O4", "Fe3O4", "ferrita magnetica", 0, 231.53, 5.17, 180, 5.0, 2.0e4, 0.10, 1597, 126, 1.95, "espinelio inverso", "#25282b"),
    ("maghemita", "Maghemita", "gamma-Fe2O3", "Fe2O3", "ferrita magnetica", 0, 159.69, 4.90, 160, 4.0, 1.0e-2, 2.00, 1565, 126, 2.00, "espinelio defeituoso", "#7c3f31"),
    ("ferrita_niquel", "Ferrita de niquel", "NiFe2O4", "NiFe2O4", "ferrita magnetica", 0, 234.38, 5.37, 170, 6.0, 1.0e-3, 1.60, 1455, 128, 1.90, "espinelio inverso", "#3d4658"),
    ("ferrita_cobalto", "Ferrita de cobalto", "CoFe2O4", "CoFe2O4", "ferrita magnetica dura", 0, 234.62, 5.30, 190, 4.5, 1.0e-4, 1.30, 1520, 128, 1.95, "espinelio inverso", "#34435e"),
    ("ferrita_manganes", "Ferrita de manganes", "MnFe2O4", "MnFe2O4", "ferrita magnetica mole", 0, 230.63, 5.00, 150, 4.0, 1.0e-2, 1.50, 1350, 130, 1.80, "espinelio", "#514a45"),
    ("ferrita_zinco", "Ferrita de zinco", "ZnFe2O4", "ZnFe2O4", "ferrita magnetica", 0, 241.07, 5.33, 160, 5.0, 1.0e-5, 1.90, 1500, 130, 1.85, "espinelio normal", "#4b5659"),
    ("ferrita_mnzn", "Ferrita MnZn", "MnZnFe2O4", "MnZnFe2O4", "ferrita magnetica mole", 0, 0, 4.90, 140, 4.5, 1.0e-2, 1.20, 1300, 132, 1.80, "espinelio", "#45494b"),
    ("ferrita_nizn", "Ferrita NiZn", "NiZnFe2O4", "NiZnFe2O4", "ferrita magnetica mole", 0, 0, 5.20, 150, 4.0, 1.0e-3, 1.40, 1350, 132, 1.85, "espinelio", "#3e4650"),
    ("hexaferrita_bario", "Hexaferrita de bario", "BaFe12O19", "BaM", "ferrita magnetica dura", 0, 1111.46, 5.28, 180, 3.5, 1.0e-8, 1.80, 1315, 155, 1.75, "magnetoplumbita hexagonal", "#4b3838"),
    ("hexaferrita_estroncio", "Hexaferrita de estroncio", "SrFe12O19", "SrM", "ferrita magnetica dura", 0, 1061.75, 5.10, 180, 3.5, 1.0e-8, 1.80, 1350, 150, 1.75, "magnetoplumbita hexagonal", "#4b3f38"),
    ("granada_ferro_itrio", "Granada de ferro e itrio", "Y3Fe5O12", "YIG", "granada ferrimagnetica", 0, 737.93, 5.17, 200, 6.0, 1.0e-12, 2.85, 1560, 160, 1.75, "granada cubica", "#637067"),
    ("granada_ferro_gadolinio", "Granada de ferro e gadolinio", "Gd3Fe5O12", "GdIG", "granada ferrimagnetica terra rara", 0, 943.0, 7.10, 190, 5.0, 1.0e-12, 2.70, 1510, 160, 1.70, "granada cubica", "#6e7569"),
    ("smco17", "Ima samario cobalto 2:17", "Sm2Co17", "Sm2Co17", "ima de terra rara", 0, 1302.0, 8.40, 150, 11.0, 8.0e5, 0.0, 1200, 160, 1.60, "romboedrica/hexagonal", "#8f7479"),
    ("terfenol_d", "Terfenol-D", "Tb0.3Dy0.7Fe2", "Terfenol-D", "liga magnetostritiva terra rara", 0, 0, 9.20, 70, 13.0, 1.0e6, 0.0, 1180, 160, 1.60, "Laves C15", "#687572"),
    ("galfenol", "Galfenol", "Fe-Ga", "FeGa", "liga magnetostritiva", 0, 0, 7.75, 80, 30.0, 8.0e6, 0.0, 1500, 128, 1.85, "bcc A2/D03", "#80847d"),
    ("permalloy", "Permalloy", "Ni80Fe20", "NiFe", "liga magnetica mole", 0, 0, 8.70, 200, 20.0, 2.0e6, 0.0, 1450, 125, 1.90, "fcc", "#7f8285"),
    ("yag_cerio", "YAG dopado com cerio", "Y3Al5O12:Ce", "YAG:Ce", "fosforo terra rara", 0, 593.62, 4.55, 280, 10.0, 1.0e-12, 6.40, 1940, 150, 1.65, "granada cubica", "#d8cf8d"),
    ("fosforo_europio_itrio", "Y2O3 dopado com europio", "Y2O3:Eu", "Y2O3:Eu", "fosforo terra rara", 0, 0, 5.05, 180, 12.0, 1.0e-12, 5.50, 2430, 160, 1.60, "bixbyita cubica", "#d98ea5"),
    ("aluminato_estroncio_europio", "Aluminato de estroncio europio disprosio", "SrAl2O4:Eu,Dy", "SrAl2O4", "fosforo persistente terra rara", 0, 0, 3.60, 150, 5.0, 1.0e-12, 5.80, 1900, 160, 1.55, "monoclinica", "#b7d48a"),
]


def add_advanced_ready_materials() -> None:
    for (
        key,
        name,
        formula,
        symbol,
        category,
        atomic_number,
        atomic_mass_u,
        density_g_cm3,
        elastic_modulus_gpa,
        thermal_conductivity_w_mk,
        electrical_conductivity_s_m,
        band_gap_ev,
        melting_point_c,
        atomic_radius_pm,
        electronegativity,
        crystal_structure,
        color,
    ) in ADVANCED_READY_MATERIALS:
        if key in LOCAL_MATERIALS:
            continue
        LOCAL_MATERIALS[key] = m(
            name=name,
            formula=formula,
            symbol=symbol,
            category=category,
            atomic_number=atomic_number,
            atomic_mass_u=atomic_mass_u,
            density_g_cm3=density_g_cm3,
            elastic_modulus_gpa=elastic_modulus_gpa,
            thermal_conductivity_w_mk=thermal_conductivity_w_mk,
            electrical_conductivity_s_m=electrical_conductivity_s_m,
            band_gap_ev=band_gap_ev,
            melting_point_c=melting_point_c,
            atomic_radius_pm=atomic_radius_pm,
            electronegativity=electronegativity,
            crystal_structure=crystal_structure,
            color=color,
        )


add_advanced_ready_materials()


PERIODIC_SYMBOL_ALIASES = {
    symbol.lower(): key
    for key, _name, symbol, *_rest in PERIODIC_TABLE_BASE
}

MATERIAL_ALIASES = {
    **PERIODIC_SYMBOL_ALIASES,
    "snse": "seleneto_estanho",
    "seleneto de estanho": "seleneto_estanho",
    "seleneto_estanho": "seleneto_estanho",
    "tin selenide": "seleneto_estanho",
    "snseo4": "selenato_estanho",
    "selenato de estanho": "selenato_estanho",
    "senelato de estanho": "selenato_estanho",
    "selenato_estanho": "selenato_estanho",
    "tin selenate": "selenato_estanho",
    "snse2": "seleneto_estanho_2",
    "disseleneto de estanho": "seleneto_estanho_2",
    "tin diselenide": "seleneto_estanho_2",
    "mos2": "sulfeto_molibdenio",
    "dissulfeto de molibdenio": "sulfeto_molibdenio",
    "molybdenum disulfide": "sulfeto_molibdenio",
    "ws2": "sulfeto_tungstenio",
    "dissulfeto de tungstenio": "sulfeto_tungstenio",
    "tungsten disulfide": "sulfeto_tungstenio",
    "hbn": "nitreto_boro",
    "h-bn": "nitreto_boro",
    "nitreto de boro": "nitreto_boro",
    "boron nitride": "nitreto_boro",
    "sno2": "oxido_estanho",
    "oxido de estanho": "oxido_estanho",
    "zno": "oxido_zinco",
    "oxido de zinco": "oxido_zinco",
    "tio2": "dioxido_titanio",
    "dioxido de titanio": "dioxido_titanio",
    "gaas": "arseneto_galio",
    "arseneto de galio": "arseneto_galio",
    "inp": "fosfeto_indio",
    "fosfeto de indio": "fosfeto_indio",
    "brass": "latao",
    "latão": "latao",
    "bronze": "bronze",
    "ss304": "aco_inoxidavel_304",
    "aco inox": "aco_inoxidavel_304",
    "aco inoxidavel": "aco_inoxidavel_304",
    "stainless steel 304": "aco_inoxidavel_304",
    "in718": "inconel_718",
    "inconel": "inconel_718",
    "sn63pb37": "solda_sn_pb",
    "solda estanho chumbo": "solda_sn_pb",
    "abs": "abs",
    "pla": "pla",
    "pet": "pet",
    "peek": "peek",
    "ptfe": "ptfe",
    "teflon": "ptfe",
    "poliimida": "poliimida",
    "polyimide": "poliimida",
    "srtio3": "titanato_estroncio",
    "titanato de estroncio": "titanato_estroncio",
    "batio3": "titanato_bario",
    "titanato de bario": "titanato_bario",
    "pbtio3": "titanato_chumbo",
    "titanato de chumbo": "titanato_chumbo",
    "catio3": "titanato_calcio",
    "titanato de calcio": "titanato_calcio",
    "laalo3": "aluminato_lantanio",
    "aluminato de lantanio": "aluminato_lantanio",
    "lsmo": "manganita_lantanio_estroncio",
    "mapbi3": "mapbi3",
    "ch3nh3pbi3": "mapbi3",
    "fapbi3": "fapbi3",
    "cspbi3": "cspbi3",
    "cspbbr3": "cspbbr3",
    "fe3o4": "magnetita",
    "magnetita": "magnetita",
    "gamma-fe2o3": "maghemita",
    "maghemita": "maghemita",
    "nife2o4": "ferrita_niquel",
    "ferrita de niquel": "ferrita_niquel",
    "cofe2o4": "ferrita_cobalto",
    "ferrita de cobalto": "ferrita_cobalto",
    "mnfe2o4": "ferrita_manganes",
    "ferrita de manganes": "ferrita_manganes",
    "znfe2o4": "ferrita_zinco",
    "ferrita de zinco": "ferrita_zinco",
    "mnzn": "ferrita_mnzn",
    "mnznfe2o4": "ferrita_mnzn",
    "nizn": "ferrita_nizn",
    "niznfe2o4": "ferrita_nizn",
    "bafe12o19": "hexaferrita_bario",
    "bam": "hexaferrita_bario",
    "hexaferrita de bario": "hexaferrita_bario",
    "srfe12o19": "hexaferrita_estroncio",
    "srm": "hexaferrita_estroncio",
    "hexaferrita de estroncio": "hexaferrita_estroncio",
    "yig": "granada_ferro_itrio",
    "y3fe5o12": "granada_ferro_itrio",
    "gdig": "granada_ferro_gadolinio",
    "gd3fe5o12": "granada_ferro_gadolinio",
    "sm2co17": "smco17",
    "terfenol-d": "terfenol_d",
    "terfenol d": "terfenol_d",
    "fega": "galfenol",
    "galfenol": "galfenol",
    "nife": "permalloy",
    "permalloy": "permalloy",
    "yag:ce": "yag_cerio",
    "y3al5o12:ce": "yag_cerio",
    "y2o3:eu": "fosforo_europio_itrio",
    "sral2o4": "aluminato_estroncio_europio",
}


def local_material_key(query: str) -> str:
    key = query.strip().lower()
    return MATERIAL_ALIASES.get(key, key)


def canonicalize_composition(
    composition: Dict[str, float],
) -> tuple[Dict[str, float], Optional[str]]:
    resolved = {local_material_key(name): fraction for name, fraction in composition.items()}
    return resolved, None


class MaterialsProjectClient:
    BASE_URL = "https://api.materialsproject.org/materials/summary"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("MP_API_KEY")

    def search_by_formula(self, formula: str) -> Optional[Material]:
        if not self.api_key or requests is None:
            return None

        headers = {"X-API-KEY": self.api_key}
        params = {
            "formula": formula,
            "fields": "formula_pretty,density,band_gap",
            "_limit": 1,
        }
        response = requests.get(self.BASE_URL, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        data = response.json().get("data", [])
        if not data:
            return None

        item = data[0]
        pretty_formula = item.get("formula_pretty", formula)
        return Material(
            name=f"Materials Project: {pretty_formula}",
            formula=pretty_formula,
            symbol=pretty_formula[:2],
            category="api",
            atomic_number=0,
            atomic_mass_u=0,
            density_g_cm3=float(item.get("density") or 0.0),
            elastic_modulus_gpa=0.0,
            thermal_conductivity_w_mk=0.0,
            electrical_conductivity_s_m=0.0,
            band_gap_ev=float(item.get("band_gap") or 0.0),
            melting_point_c=0.0,
            atomic_radius_pm=100,
            electronegativity=0.0,
            crystal_structure="desconhecida",
            color="#7b8da6",
            source="materials_project",
        )


def get_material(query: str, client: MaterialsProjectClient) -> Material:
    key = local_material_key(query)
    if key in LOCAL_MATERIALS:
        return LOCAL_MATERIALS[key]

    api_material = client.search_by_formula(query)
    if api_material:
        return api_material

    available = ", ".join(sorted(LOCAL_MATERIALS))
    raise ValueError(f"Material '{query}' nao encontrado. Materiais locais: {available}.")


def normalize_fractions(composition: Dict[str, float]) -> Dict[str, float]:
    total = sum(composition.values())
    if total <= 0:
        raise ValueError("A soma das fracoes deve ser maior que zero.")
    return {name: fraction / total for name, fraction in composition.items()}


def weighted_average(materials: Iterable[tuple[Material, float]], attr: str) -> float:
    values = []
    for material, fraction in materials:
        value = getattr(material, attr)
        if value > 0:
            values.append(value * fraction)
    return sum(values)


def estimate_seebeck_uv_k(material: Material) -> float:
    formula = material.formula.lower()
    category = material.category.lower()
    name = material.name.lower()

    values = {
        "bi2te3": 220.0,
        "pbte": 180.0,
        "cdte": 100.0,
        "snte": 120.0,
        "snse": 520.0,
        "sic": 250.0,
        "si": 440.0,
        "ge": 330.0,
        "p": 350.0,
        "al2o3": 0.0,
    }
    if formula in values:
        return values[formula]
    if "grafeno" in name or "graphene" in name:
        return 80.0
    if "semicondutor" in category or material.band_gap_ev > 0.1:
        return 180.0
    if "metal" in category or material.electrical_conductivity_s_m > 1.0e6:
        return 8.0
    if "ceramico" in category:
        return 40.0
    return 25.0


def thermoelectric_values(material: Material) -> dict[str, float]:
    seebeck_uv_k = estimate_seebeck_uv_k(material)
    seebeck_v_k = seebeck_uv_k * 1.0e-6
    sigma = material.electrical_conductivity_s_m
    thermal = max(material.thermal_conductivity_w_mk, 1.0e-9)
    power_factor = seebeck_v_k * seebeck_v_k * sigma
    zt_300k = power_factor * 300 / thermal
    return {
        "seebeck_uv_k": seebeck_uv_k,
        "fator_potencia_w_mk2": power_factor,
        "zt_300k": zt_300k,
    }


def dominant_structure(selected: list[tuple[Material, float]]) -> str:
    totals: dict[str, float] = {}
    for material, fraction in selected:
        totals[material.crystal_structure] = totals.get(material.crystal_structure, 0) + fraction
    return max(totals.items(), key=lambda item: item[1])[0]


def estimate_lattice_a_angstrom(material: Material) -> float:
    radius_a = max(material.atomic_radius_pm, 80) / 100
    structure = material.crystal_structure.lower()
    if "fcc" in structure:
        return 2 * math.sqrt(2) * radius_a
    if "bcc" in structure:
        return 4 * radius_a / math.sqrt(3)
    if "diamante" in structure:
        return 8 * radius_a / math.sqrt(3)
    if "hcp" in structure or "hexagonal" in structure:
        return 2 * radius_a
    return 2.5 * radius_a


def cubic_hkl_for_structure(structure: str) -> list[tuple[int, int, int, float]]:
    structure = structure.lower()
    if "perovskita" in structure:
        return [(1, 0, 0, 18), (1, 1, 0, 100), (1, 1, 1, 22), (2, 0, 0, 45), (2, 1, 0, 26), (2, 1, 1, 16), (2, 2, 0, 12)]
    if "espinelio" in structure:
        return [(2, 2, 0, 35), (3, 1, 1, 100), (4, 0, 0, 45), (4, 2, 2, 55), (5, 1, 1, 20), (4, 4, 0, 30), (5, 3, 3, 12)]
    if "granada" in structure:
        return [(4, 2, 0, 34), (4, 2, 2, 100), (4, 4, 4, 45), (6, 4, 0, 28), (6, 4, 2, 22), (8, 4, 0, 14)]
    if "magnetoplumbita" in structure or "hexaferrita" in structure:
        return [(1, 0, 7, 22), (1, 1, 4, 55), (2, 0, 3, 100), (2, 0, 5, 45), (2, 1, 7, 30), (2, 2, 0, 18)]
    if "fcc" in structure:
        return [(1, 1, 1, 100), (2, 0, 0, 54), (2, 2, 0, 32), (3, 1, 1, 28), (2, 2, 2, 14), (4, 0, 0, 10)]
    if "bcc" in structure:
        return [(1, 1, 0, 100), (2, 0, 0, 22), (2, 1, 1, 35), (2, 2, 0, 15), (3, 1, 0, 9), (2, 2, 2, 6)]
    if "diamante" in structure:
        return [(1, 1, 1, 100), (2, 2, 0, 55), (3, 1, 1, 32), (4, 0, 0, 9), (3, 3, 1, 18), (4, 2, 2, 12)]
    if "hcp" in structure or "hexagonal" in structure:
        return [(1, 0, 0, 42), (0, 0, 2, 55), (1, 0, 1, 100), (1, 0, 2, 35), (1, 1, 0, 28), (1, 0, 3, 18)]
    return [(1, 0, 0, 70), (1, 1, 0, 45), (1, 1, 1, 32), (2, 0, 0, 22), (2, 1, 0, 15)]


ORTHORHOMBIC_LATTICE_A = {
    "SnSe": (11.50, 4.15, 4.44),
}


def orthorhombic_hkl() -> list[tuple[int, int, int, float]]:
    return [
        (1, 1, 1, 100),
        (4, 0, 0, 75),
        (2, 0, 1, 58),
        (4, 0, 1, 46),
        (0, 2, 0, 38),
        (4, 1, 1, 30),
        (6, 0, 0, 22),
        (0, 0, 2, 18),
    ]


def orthorhombic_d_spacing_a(
    h: int,
    k: int,
    l: int,
    lattice: tuple[float, float, float],
) -> float:
    a, b, c = lattice
    reciprocal = (h * h) / (a * a) + (k * k) / (b * b) + (l * l) / (c * c)
    return 1 / math.sqrt(reciprocal)


def estimate_xrd_peaks(selected: list[tuple[Material, float]]) -> list[dict[str, Any]]:
    wavelength_a = 1.5406  # Cu K-alpha, angstrom
    peaks: list[dict[str, Any]] = []

    for material, fraction in selected:
        if material.formula in ORTHORHOMBIC_LATTICE_A:
            lattice = ORTHORHOMBIC_LATTICE_A[material.formula]
            hkls = orthorhombic_hkl()
            d_spacing_for = lambda h, k, l: orthorhombic_d_spacing_a(h, k, l, lattice)
        else:
            a = estimate_lattice_a_angstrom(material)
            hkls = cubic_hkl_for_structure(material.crystal_structure)
            d_spacing_for = lambda h, k, l: a / math.sqrt(h * h + k * k + l * l)

        for h, k, l, base_intensity in hkls:
            d_spacing = d_spacing_for(h, k, l)
            ratio = wavelength_a / (2 * d_spacing)
            if ratio <= 0 or ratio >= 1:
                continue
            two_theta = 2 * math.degrees(math.asin(ratio))
            if 5 <= two_theta <= 95:
                peaks.append(
                    {
                        "material": material.name,
                        "symbol": material.symbol,
                        "hkl": f"{h}{k}{l}",
                        "two_theta_deg": round(two_theta, 2),
                        "d_spacing_a": round(d_spacing, 4),
                        "intensity": round(base_intensity * fraction, 2),
                        "color": material.color,
                    }
                )

    peaks.sort(key=lambda peak: peak["two_theta_deg"])
    max_intensity = max((peak["intensity"] for peak in peaks), default=1)
    for peak in peaks:
        peak["relative_intensity"] = round(100 * peak["intensity"] / max_intensity, 2)
    return peaks[:24]


def simulate_composite(
    composition: Dict[str, float],
    client: Optional[MaterialsProjectClient] = None,
) -> Dict[str, Any]:
    client = client or MaterialsProjectClient()
    composition, _compound_message = canonicalize_composition(composition)
    fractions = normalize_fractions(composition)
    selected = [(get_material(name, client), frac) for name, frac in fractions.items()]

    density = weighted_average(selected, "density_g_cm3")
    modulus = weighted_average(selected, "elastic_modulus_gpa")
    thermal = weighted_average(selected, "thermal_conductivity_w_mk")
    electrical = weighted_average(selected, "electrical_conductivity_s_m")
    band_gap = weighted_average(selected, "band_gap_ev")
    melting_point = weighted_average(selected, "melting_point_c")
    atomic_radius = weighted_average(selected, "atomic_radius_pm")
    electronegativity = weighted_average(selected, "electronegativity")
    hardness = weighted_average(selected, "hardness_vickers_hv")
    seebeck = sum(estimate_seebeck_uv_k(material) * fraction for material, fraction in selected)
    seebeck_v_k = seebeck * 1.0e-6
    power_factor = seebeck_v_k * seebeck_v_k * electrical
    zt_300k = power_factor * 300 / thermal if thermal > 0 else 0

    return {
        "formula_aproximada": " + ".join(
            f"{fraction:.2f}*{material.formula}" for material, fraction in selected
        ),
        "densidade_g_cm3": round(density, 3),
        "modulo_elastico_gpa": round(modulus, 3),
        "condutividade_termica_w_mk": round(thermal, 3),
        "condutividade_eletrica_s_m": round(electrical, 6),
        "resistividade_ohm_m": round(1 / electrical, 12) if electrical > 0 else "n/a",
        "band_gap_ev": round(band_gap, 3),
        "ponto_fusao_c": round(melting_point, 1),
        "raio_atomico_pm": round(atomic_radius, 1),
        "eletronegatividade_media": round(electronegativity, 3),
        "dureza_vickers_hv": round(hardness, 1),
        "seebeck_uv_k": round(seebeck, 3),
        "fator_potencia_w_mk2": round(power_factor, 8),
        "zt_300k": round(zt_300k, 4),
        "estrutura_predominante": dominant_structure(selected),
        "classe_eletrica": classify_electrical_behavior(band_gap, electrical),
        "indicacao": suggest_application(density, modulus, thermal, electrical, band_gap),
        "componentes": [
            {
                **material.to_dict(),
                "fraction": round(fraction, 4),
                **{
                    key: round(value, 8)
                    for key, value in thermoelectric_values(material).items()
                },
            }
            for material, fraction in selected
        ],
        "xrd": {
            "radiacao": "Cu K-alpha",
            "comprimento_onda_a": 1.5406,
            "observacao": "picos aproximados calculados por lei de Bragg e rede idealizada",
            "picos": estimate_xrd_peaks(selected),
        },
    }


def classify_electrical_behavior(band_gap_ev: float, conductivity: float) -> str:
    if conductivity >= 1.0e6 or band_gap_ev < 0.1:
        return "condutor"
    if conductivity >= 1.0e-6 or band_gap_ev < 3.0:
        return "semicondutor"
    return "isolante"


def suggest_application(
    density: float,
    modulus: float,
    thermal: float,
    electrical: float,
    band_gap: float,
) -> str:
    if electrical > 1.0e7 and thermal > 150:
        return "bom candidato para trilhas condutoras, contatos e dissipacao termica"
    if band_gap >= 3.0 and electrical < 1.0e-6:
        return "bom candidato para isolamento eletrico e barreiras dieletricas"
    if modulus > 140 and density < 5.0:
        return "bom candidato estrutural leve ou reforco de composite"
    if thermal > 100 and electrical < 1.0:
        return "bom candidato para dissipacao termica com isolamento eletrico"
    return "candidato generico; refine com dados experimentais e simulacoes dedicadas"


def print_report(result: Dict[str, Any]) -> None:
    print("\nResultado da simulacao")
    print("-" * 24)
    for key, value in result.items():
        if key == "componentes":
            continue
        label = key.replace("_", " ").capitalize()
        print(f"{label}: {value}")


def main() -> None:
    print("Materiais locais disponiveis:")
    print(", ".join(sorted(LOCAL_MATERIALS)))
    result = simulate_composite({"aluminio": 0.70, "cobre": 0.30})
    print_report(result)


if __name__ == "__main__":
    main()
