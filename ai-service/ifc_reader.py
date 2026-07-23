"""Lecture des maquettes BIM (.ifc) — la voie fiable.

Différence de fond avec le DXF : ici on ne devine rien. Une pièce est un objet
`IfcSpace` qui porte son nom et sa surface ; une porte est un `IfcDoor` qui
porte sa largeur en attribut. Là où le DXF obligeait à supposer « polyligne
fermée = pièce » (et produisait 100 % de faux positifs sur un plan réel), l'IFC
donne la réponse directement.

C'est ce qui rend l'analyse exploitable sur de vrais projets. La contrainte :
le fichier doit venir d'un outil BIM (ArchiCAD, Revit), pas d'un DAO 2D.
"""

import os
import tempfile

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.unit

# Bornes de sécurité : même en IFC, un modèle peut contenir des espaces
# techniques aberrants (vides, gaines). On ne rejette pas, on signale.
_MAX_ITEMS = 500

# Noms de quantités normalisées, par ordre de préférence.
_AREA_KEYS = ("NetFloorArea", "GrossFloorArea", "NetArea", "GrossArea")
_HEIGHT_KEYS = ("FinishCeilingHeight", "Height", "NetHeight", "GrossHeight")


def _quantity(element, keys) -> float | None:
    """Cherche une quantité normalisée (Qto_*) parmi plusieurs noms possibles."""
    try:
        psets = ifcopenshell.util.element.get_psets(element)
    except Exception:
        return None
    for values in psets.values():
        for key in keys:
            value = values.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
    return None


def _placement_xy(placement) -> tuple[float, float]:
    """Translation (x, y) d'un IfcLocalPlacement, en cumulant les parents."""
    x, y = 0.0, 0.0
    seen = 0
    while placement is not None and seen < 20:  # garde-fou anti-boucle
        seen += 1
        try:
            loc = placement.RelativePlacement.Location.Coordinates
            x += float(loc[0])
            y += float(loc[1])
        except Exception:
            pass
        placement = getattr(placement, "PlacementRelTo", None)
    return x, y


def _footprint(space) -> list[tuple[float, float]] | None:
    """Emprise 2D (contour) d'une pièce, si sa géométrie est un profil extrudé.

    Beaucoup d'IFC réels décrivent les pièces ainsi ; sinon (IFC de quantités,
    géométrie complexe), on renvoie None et l'affichage retombe sur le schéma."""
    try:
        representation = space.Representation
        if not representation:
            return None
        ox, oy = _placement_xy(space.ObjectPlacement)
        for rep in representation.Representations:
            for item in rep.Items:
                if not item.is_a("IfcExtrudedAreaSolid"):
                    continue
                profile = item.SweptArea
                if not profile.is_a("IfcArbitraryClosedProfileDef"):
                    continue
                curve = profile.OuterCurve
                if not curve.is_a("IfcPolyline"):
                    continue
                pts = [
                    (float(p.Coordinates[0]) + ox, float(p.Coordinates[1]) + oy)
                    for p in curve.Points
                ]
                # Retirer le point de fermeture s'il duplique le premier.
                if len(pts) > 2 and pts[0] == pts[-1]:
                    pts = pts[:-1]
                return pts if len(pts) >= 3 else None
    except Exception:
        return None
    return None


def _space_label(space) -> str:
    """Nom lisible d'une pièce : LongName est souvent le libellé métier."""
    for attr in ("LongName", "Name"):
        value = getattr(space, attr, None)
        if value:
            return str(value).strip()
    return "sans nom"


def extract_measurements(raw: bytes) -> dict:
    """Extrait les grandeurs vérifiables d'une maquette IFC."""
    handle, path = tempfile.mkstemp(suffix=".ifc")
    try:
        with os.fdopen(handle, "wb") as tmp:
            tmp.write(raw)
        model = ifcopenshell.open(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    # Facteur de conversion vers le mètre, déclaré par le modèle lui-même.
    try:
        to_meter = float(ifcopenshell.util.unit.calculate_unit_scale(model))
    except Exception:
        to_meter = 1.0

    # --- Pièces : lues, pas devinées ------------------------------------
    rooms: list[dict] = []
    room_areas: list[float] = []
    for space in model.by_type("IfcSpace")[:_MAX_ITEMS]:
        area = _quantity(space, _AREA_KEYS)
        if area is None:
            continue
        # Les quantités IFC sont déjà en unités du projet : on convertit les
        # surfaces avec le carré du facteur.
        area_m2 = round(area * (to_meter ** 2), 3)
        if area_m2 <= 0:
            continue
        height = _quantity(space, _HEIGHT_KEYS)
        footprint = _footprint(space)
        rooms.append(
            {
                "name": _space_label(space),
                "area_m2": area_m2,
                "height_m": round(height * to_meter, 3) if height else None,
                # Emprise réelle (m) si le modèle porte sa géométrie, sinon None.
                "footprint": (
                    [[round(x * to_meter, 3), round(y * to_meter, 3)] for x, y in footprint]
                    if footprint
                    else None
                ),
            }
        )
        room_areas.append(area_m2)

    # --- Portes et fenêtres : largeur portée par l'objet -----------------
    door_widths: list[float] = []
    for door in model.by_type("IfcDoor")[:_MAX_ITEMS]:
        width = getattr(door, "OverallWidth", None)
        if isinstance(width, (int, float)) and width > 0:
            door_widths.append(round(float(width) * to_meter, 3))

    window_widths: list[float] = []
    for window in model.by_type("IfcWindow")[:_MAX_ITEMS]:
        width = getattr(window, "OverallWidth", None)
        if isinstance(width, (int, float)) and width > 0:
            window_widths.append(round(float(window.OverallWidth) * to_meter, 3))

    storeys = [
        str(getattr(s, "Name", "") or "").strip()
        for s in model.by_type("IfcBuildingStorey")
    ]

    counts = {
        "IfcSpace": len(model.by_type("IfcSpace")),
        "IfcDoor": len(model.by_type("IfcDoor")),
        "IfcWindow": len(model.by_type("IfcWindow")),
        "IfcWall": len(model.by_type("IfcWall")),
        "IfcStair": len(model.by_type("IfcStair")),
    }

    room_areas.sort()
    return {
        "source": "ifc",  # les pièces sont fiables : le moteur peut leur faire confiance
        "schema": getattr(model, "schema", "inconnu"),
        "unit": "m",
        "to_meter_factor": 1.0,  # tout est déjà converti en mètres ci-dessus
        "rooms": rooms,
        "room_areas_m2": room_areas,
        "dimensions": door_widths,  # les largeurs de porte sont des cotes certaines
        "door_widths_m": door_widths,
        "window_widths_m": window_widths,
        "storeys": storeys,
        "entity_counts": counts,
        "texts": [r["name"] for r in rooms],
        "extents": None,
        "categories": {},
        "layers": [],
        "blocks": {},
    }


def to_prompt_text(m: dict) -> str:
    """Met en forme la maquette pour le modèle (mode VECTOR)."""
    lines = [f"Maquette BIM ({m['schema']}), grandeurs lues directement du modèle."]

    if m["storeys"]:
        lines.append(f"Niveaux : {', '.join(n for n in m['storeys'] if n)}")

    if m["rooms"]:
        detail = "; ".join(
            f"{r['name']} : {r['area_m2']} m²"
            + (f", h {r['height_m']} m" if r["height_m"] else "")
            for r in m["rooms"][:80]
        )
        lines.append(f"Pièces ({len(m['rooms'])}) : {detail}")

    if m["door_widths_m"]:
        vals = ", ".join(f"{w} m" for w in sorted(set(m["door_widths_m"]))[:40])
        lines.append(f"Largeurs de portes : {vals}")

    if m["window_widths_m"]:
        vals = ", ".join(f"{w} m" for w in sorted(set(m["window_widths_m"]))[:40])
        lines.append(f"Largeurs de fenêtres : {vals}")

    counts = ", ".join(f"{k}:{v}" for k, v in m["entity_counts"].items() if v)
    lines.append(f"Objets : {counts}")
    return "\n".join(lines)
