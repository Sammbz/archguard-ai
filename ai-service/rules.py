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


def _describe(
    reg: regulations.Regulation, measured: float, subject: str, gap: float, unit: str
) -> str:
    """Formule le constat, avec l'écart chiffré pour le rendre actionnable."""
    base = (
        f"{subject} : {measured} {unit} mesurés pour un minimum de "
        f"{reg.threshold} {unit} — {reg.label}"
    )
    ecart = f" Écart : il manque {gap} {unit}."
    if reg.validated and reg.code_reference:
        return f"{base}. Non conforme ({reg.code_reference}).{ecart}"
    return f"{base}. Repère non réglementaire, à valider.{ecart}"


def _finding(
    reg: regulations.Regulation,
    measured: float,
    subject: str,
    unit: str,
    target: str | None = None,
) -> dict:
    # Écart = ce qui manque pour atteindre le seuil. On ne conçoit pas la
    # correction (choix d'architecte), on donne juste l'objectif chiffré.
    gap = round(reg.threshold - measured, 3)
    return {
        "type": reg.axis,
        "severity": reg.severity,
        "description": _describe(reg, measured, subject, gap, unit),
        "measured": measured,
        "threshold": reg.threshold,
        "gap": gap,
        "unit": unit,
        "target": target,  # nom de la pièce visée, pour la carte de conformité
        "code_reference": reg.code_reference if reg.validated else None,
        "validated": reg.validated,
        "certain": True,  # la mesure est certaine, distincte de l'estimation IA
    }


def _dimension_values(measurements: dict, concern: str) -> list[float]:
    """Cotes à confronter à une règle, selon la source.

    En IFC, les mesures sont typées (largeur de porte vs de fenêtre) : on route
    chaque règle vers son sujet, donc pas de double comptage — une largeur de
    porte n'est pas testée comme une circulation. En DXF, on n'a que des cotes
    anonymes : faute de savoir ce qu'elles représentent, toutes les règles
    dimensionnelles s'y appliquent (d'où un possible double signalement, assumé)."""
    if measurements.get("source") == "ifc":
        typed = {
            "largeur_porte": measurements.get("door_widths_m", []),
            "largeur_circulation": measurements.get("circulation_widths_m", []),
        }
        return typed.get(concern, [])
    return measurements.get("dimensions", [])


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
            rooms = measurements.get("rooms")
            if rooms:
                # Source IFC : la pièce est un objet du modèle, avec son nom et
                # sa surface. Aucun garde-fou de plausibilité nécessaire — on ne
                # devine plus, donc plus de faux positifs à filtrer.
                for room in rooms:
                    area = room.get("area_m2")
                    if area is not None and area < reg.threshold:
                        findings.append(
                            _finding(
                                reg, area, f"Pièce « {room['name']} »", "m²",
                                target=room["name"],
                            )
                        )
            else:
                # Source DXF : « polyligne fermée = pièce » est une supposition.
                for area in measurements.get("room_areas_m2", []):
                    if not ROOM_PLAUSIBLE_MIN_M2 <= area <= ROOM_PLAUSIBLE_MAX_M2:
                        continue
                    if area < reg.threshold:
                        findings.append(_finding(reg, area, "Espace fermé", "m²"))

        elif reg.kind == "min_ceiling_height":
            # Activable seulement avec une source qui porte la hauteur (IFC) :
            # un plan 2D n'en contient pas.
            for room in measurements.get("rooms", []):
                height = room.get("height_m")
                if height is not None and height < reg.threshold:
                    findings.append(
                        _finding(
                            reg, height, f"Pièce « {room['name']} » (hauteur)", "m",
                            target=room["name"],
                        )
                    )

        elif reg.kind == "min_dimension":
            subject = "Porte" if reg.concern == "largeur_porte" else "Cote"
            for dim in _dimension_values(measurements, reg.concern):
                # On compare la valeur BRUTE : arrondir avant la comparaison
                # ferait passer 0,899 m pour 0,90 m et masquerait la
                # non-conformité. L'arrondi ne sert qu'à l'affichage.
                dim_m = dim * factor
                if 0 < dim_m < reg.threshold:
                    shown = round(dim_m, 3)
                    findings.append(_finding(reg, shown, subject, "m"))

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
