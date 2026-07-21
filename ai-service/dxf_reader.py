"""Lecture vectorielle des fichiers CAO (.dxf) — brique du « Niveau 3 ».

Au lieu de rasteriser le plan et de laisser le modèle deviner les cotes à
l'œil, on lit le fichier et on en extrait des MESURES EXACTES : dimensions
cotées, textes (pièces, surfaces), blocs (portes/fenêtres), emprise générale.
Ces valeurs certaines sont ensuite passées au modèle (voir SYSTEM_PROMPT_VECTOR).

Limites assumées de cette première version :
- Seul le .dxf (format ouvert) est lu. Le .dwg natif doit d'abord être converti.
- On extrait ce qui est générique (cotes, textes, blocs, calques). Reconnaître
  « ce polyligne est un mur porteur » dépend des conventions de chaque cabinet
  et reste le gros chantier restant.
"""

import io

import ezdxf
from ezdxf import bbox
from ezdxf.recover import read as recover_read

# Borne le volume envoyé au modèle : au-delà, le coût en tokens grimpe sans
# gain d'analyse. On garde les premiers éléments rencontrés.
_MAX_ITEMS = 250

# $INSUNITS : code d'unité du dessin -> (libellé, facteur vers le mètre).
_UNITS = {
    0: ("sans unité", None),
    1: ("pouces", 0.0254),
    2: ("pieds", 0.3048),
    4: ("mm", 0.001),
    5: ("cm", 0.01),
    6: ("m", 1.0),
    8: ("microns", 1e-6),
    9: ("dm", 0.1),
    14: ("dam", 10.0),
}


def _polygon_area(points) -> float:
    """Surface d'un polygone fermé (formule de Gauss / shoelace), en valeur
    absolue et dans les unités du dessin."""
    n = len(points)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = points[i][0], points[i][1]
        x2, y2 = points[(i + 1) % n][0], points[(i + 1) % n][1]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _room_areas(msp, to_meter) -> list[float]:
    """Surfaces (m²) des polylignes fermées : la donnée que le mode image ne
    peut jamais mesurer exactement. Sans unité connue, on ne convertit pas."""
    if not to_meter:
        return []
    areas: list[float] = []
    for poly in msp.query("LWPOLYLINE POLYLINE"):
        try:
            if not poly.is_closed:
                continue
            pts = [(p[0], p[1]) for p in poly.get_points()] if poly.dxftype() == "LWPOLYLINE" \
                else [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
        except Exception:
            continue
        # float() natif : ezdxf renvoie des np.float64, à éviter côté JSONB.
        area_m2 = round(float(_polygon_area(pts)) * (to_meter ** 2), 2)
        if area_m2 > 0:
            areas.append(area_m2)
    return sorted(areas)


# Classification heuristique par mots-clés dans les noms de calques/blocs.
# Première passe du « sens » des entités : imparfaite (les conventions varient
# d'un cabinet à l'autre) mais déjà utile comme contexte. Le vrai chantier de
# reconnaissance géométrique reste à faire.
_CATEGORY_KEYWORDS = {
    "murs": ("mur", "wall", "cloison"),
    "portes": ("porte", "door", "prt"),
    "fenetres": ("fenetre", "fenêtre", "window", "baie", "wind"),
    "escaliers": ("escalier", "stair", "esc", "marche"),
    "cotation": ("cotation", "cote", "dim", "anno-dim"),
    "mobilier": ("mobilier", "meuble", "furn", "equip"),
    "reseaux": ("elec", "plomb", "sanit", "hvac", "clim"),
}


def _classify(names: list[str]) -> dict[str, list[str]]:
    """Range des noms (calques ou blocs) par catégorie selon des mots-clés."""
    result: dict[str, list[str]] = {}
    for name in names:
        low = name.lower()
        for category, keywords in _CATEGORY_KEYWORDS.items():
            if any(k in low for k in keywords):
                result.setdefault(category, []).append(name)
                break
    return result


def _plain_text(entity) -> str:
    """Texte lisible d'un TEXT ou MTEXT, sans codes de formatage."""
    try:
        if entity.dxftype() == "MTEXT":
            return entity.plain_text().strip()
        return str(entity.dxf.text).strip()
    except Exception:
        return ""


def extract_measurements(raw: bytes) -> dict:
    """Extrait un résumé structuré des données mesurables d'un .dxf."""
    # recover.read tolère les fichiers légèrement malformés, fréquents en vrai.
    doc, _auditor = recover_read(io.BytesIO(raw))
    msp = doc.modelspace()

    unit_code = int(doc.header.get("$INSUNITS", 0) or 0)
    unit_label, to_meter = _UNITS.get(unit_code, ("inconnue", None))

    # Emprise générale du dessin.
    extents = None
    try:
        box = bbox.extents(msp)
        if box.has_data:
            size = box.size  # Vec3 en unités du dessin
            extents = {"width": round(size.x, 3), "height": round(size.y, 3)}
    except Exception:
        pass

    # Cotes réellement portées sur le plan : la donnée la plus fiable.
    dimensions = []
    for dim in msp.query("DIMENSION"):
        try:
            value = dim.get_measurement()
        except Exception:
            continue
        if isinstance(value, (int, float)):
            dimensions.append(round(float(value), 3))
        if len(dimensions) >= _MAX_ITEMS:
            break

    # Textes du plan : noms de pièces, surfaces annotées, notes.
    texts = []
    for txt in msp.query("TEXT MTEXT"):
        content = _plain_text(txt)
        if content:
            texts.append(content)
        if len(texts) >= _MAX_ITEMS:
            break

    # Blocs insérés : portes, fenêtres, sanitaires… comptés par nom.
    blocks: dict[str, int] = {}
    for ref in msp.query("INSERT"):
        try:
            name = ref.dxf.name
        except Exception:
            continue
        blocks[name] = blocks.get(name, 0) + 1

    # Comptage global par type d'entité — donne la « densité » du dessin.
    entity_counts: dict[str, int] = {}
    for entity in msp:
        t = entity.dxftype()
        entity_counts[t] = entity_counts.get(t, 0) + 1

    layers = [layer.dxf.name for layer in doc.layers]
    room_areas = _room_areas(msp, to_meter)
    # Sens probable des calques/blocs (heuristique par nom).
    categories = _classify(layers + list(blocks.keys()))

    return {
        "unit": unit_label,
        "to_meter_factor": to_meter,
        "extents": extents,
        "dimensions": dimensions,
        "room_areas_m2": room_areas,
        "texts": texts,
        "blocks": blocks,
        "entity_counts": entity_counts,
        "layers": layers,
        "categories": categories,
    }


def to_prompt_text(m: dict) -> str:
    """Met en forme le résumé pour l'envoyer au modèle (mode VECTOR)."""
    lines = [f"Unité du dessin : {m['unit']}"]

    if m["extents"]:
        w, h = m["extents"]["width"], m["extents"]["height"]
        line = f"Emprise du dessin : {w} x {h} (unités du dessin)"
        if m["to_meter_factor"]:
            line += f"  ≈ {round(w * m['to_meter_factor'], 2)} x {round(h * m['to_meter_factor'], 2)} m"
        lines.append(line)

    if m["dimensions"]:
        vals = ", ".join(str(d) for d in m["dimensions"][:80])
        lines.append(f"Cotes relevées ({len(m['dimensions'])}) : {vals}")

    if m.get("room_areas_m2"):
        vals = ", ".join(f"{a} m²" for a in m["room_areas_m2"][:60])
        lines.append(f"Surfaces des espaces fermés ({len(m['room_areas_m2'])}) : {vals}")

    if m["blocks"]:
        blocks = ", ".join(f"{name} x{n}" for name, n in m["blocks"].items())
        lines.append(f"Blocs insérés : {blocks}")

    if m["texts"]:
        joined = " | ".join(m["texts"][:120])
        lines.append(f"Textes du plan : {joined}")

    if m.get("categories"):
        cats = "; ".join(
            f"{cat} ({', '.join(names[:8])})" for cat, names in m["categories"].items()
        )
        lines.append(f"Éléments identifiés (heuristique, à confirmer) : {cats}")

    if m["layers"]:
        lines.append(f"Calques : {', '.join(m['layers'][:60])}")

    if m["entity_counts"]:
        counts = ", ".join(f"{t}:{n}" for t, n in m["entity_counts"].items())
        lines.append(f"Entités : {counts}")

    return "\n".join(lines)
