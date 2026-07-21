"""Moteur de règles déterministe — cœur du « Niveau 3 ».

Ici, pas d'IA : on compare des mesures EXACTES (issues du .dxf) aux seuils du
catalogue (regulations.py). Le moteur est générique — il ne connaît aucun pays.
Ingérer un code = ajouter des entrées dans regulations.py, pas modifier ce code.

Un constat n'est présenté comme non-conformité réglementaire (avec article) que
si la règle est `validated`. Sinon, c'est un « point d'attention à valider ».
"""

import regulations


def _describe(reg: regulations.Regulation, measured: float, subject: str) -> str:
    """Formule le constat selon que la règle est validée (droit) ou non (repère)."""
    base = (
        f"{subject} : {measured} (mesuré) pour un minimum de "
        f"{reg.threshold} — {reg.label}"
    )
    if reg.validated and reg.code_reference:
        return f"{base}. Non conforme ({reg.code_reference})."
    return f"{base}. Repère non réglementaire, à valider."


def _finding(reg: regulations.Regulation, measured: float, subject: str) -> dict:
    return {
        "type": reg.axis,
        "severity": reg.severity,
        "description": _describe(reg, measured, subject),
        "measured": measured,
        "threshold": reg.threshold,
        "code_reference": reg.code_reference if reg.validated else None,
        "validated": reg.validated,
        "certain": True,  # la mesure est certaine, distincte de l'estimation IA
    }


def evaluate(measurements: dict, country: str = regulations.GENERIC) -> list[dict]:
    """Applique les règles du pays aux mesures extraites du .dxf.

    N'émet un constat que si la mesure est fiable ET l'unité connue (sinon on ne
    peut pas comparer à un seuil métrique)."""
    if measurements.get("to_meter_factor") is None:
        return []
    factor = measurements["to_meter_factor"]
    findings: list[dict] = []

    for reg in regulations.for_country(country):
        if reg.kind == "min_room_area":
            for area in measurements.get("room_areas_m2", []):
                if area < reg.threshold:
                    findings.append(
                        _finding(reg, area, f"Espace fermé de {area} m²")
                    )

        elif reg.kind == "min_dimension":
            for dim in measurements.get("dimensions", []):
                dim_m = round(dim * factor, 2)
                if 0 < dim_m < reg.threshold:
                    findings.append(
                        _finding(reg, dim_m, f"Cote de {dim_m} m")
                    )

    return findings
