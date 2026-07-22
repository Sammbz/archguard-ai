"""Moteur de règles déterministe — cœur du « Niveau 3 ».

Ici, pas d'IA : on compare des mesures EXACTES (issues du .dxf) aux seuils du
catalogue (regulations.py). Le moteur est générique — il ne connaît aucun pays.
Ingérer un code = ajouter des entrées dans regulations.py, pas modifier ce code.

Un constat n'est présenté comme non-conformité réglementaire (avec article) que
si la règle est `validated`. Sinon, c'est un « point d'attention à valider ».
"""

import regulations

# Fenêtre de plausibilité d'une pièce. Hors de ces bornes, une polyligne fermée
# n'est presque jamais une pièce : mobilier, symbole, hachure et débattement de
# porte en dessous ; cartouche, limite de parcelle et géométrie parasite au
# dessus. Sans ce garde-fou, un plan réel produit des milliers de faux constats
# (mesuré : 1727 sur un fichier de projet, dont 100 % de faux positifs).
ROOM_PLAUSIBLE_MIN_M2 = 1.5
ROOM_PLAUSIBLE_MAX_M2 = 500.0

# Un rapport lisible prime sur l'exhaustivité : au-delà, c'est un mur de bruit.
MAX_FINDINGS = 25
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


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
                # Écarter ce qui ne peut pas être une pièce avant de comparer.
                if not ROOM_PLAUSIBLE_MIN_M2 <= area <= ROOM_PLAUSIBLE_MAX_M2:
                    continue
                if area < reg.threshold:
                    findings.append(
                        _finding(reg, area, f"Espace fermé de {area} m²")
                    )

        elif reg.kind == "min_dimension":
            for dim in measurements.get("dimensions", []):
                # On compare la valeur BRUTE : arrondir avant la comparaison
                # ferait passer 0,899 m pour 0,90 m et masquerait la
                # non-conformité. L'arrondi ne sert qu'à l'affichage.
                dim_m = dim * factor
                if 0 < dim_m < reg.threshold:
                    shown = round(dim_m, 3)
                    findings.append(_finding(reg, shown, f"Cote de {shown} m"))

    # Les plus graves d'abord, puis on borne : un rapport de 1700 lignes ne se
    # lit pas. Le nombre total reste disponible via le champ « truncated ».
    findings.sort(key=lambda f: _SEVERITY_ORDER.get(f["severity"], 3))
    if len(findings) > MAX_FINDINGS:
        kept = findings[:MAX_FINDINGS]
        kept.append(
            {
                "type": "dimensions",
                "severity": "low",
                "description": (
                    f"{len(findings) - MAX_FINDINGS} autres écarts mesurés non "
                    f"détaillés. Beaucoup peuvent être des faux positifs : le "
                    f"moteur ne distingue pas encore une pièce d'un meuble."
                ),
                "measured": None,
                "threshold": None,
                "code_reference": None,
                "validated": False,
                "certain": True,
                "truncated": len(findings) - MAX_FINDINGS,
            }
        )
        return kept
    return findings
