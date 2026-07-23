"""Carte de conformité — un schéma SVG des pièces, coloré par conformité.

Honnêteté du procédé : ce n'est PAS le dessin réel du plan (il faudrait la
géométrie du fichier, absente d'un IFC de quantités). C'est une carte
schématique : une case par pièce, taille proportionnelle à la surface, verte si
conforme, rouge si non conforme, avec l'écart. Elle montre *où* et *de combien*,
d'un coup d'œil — sans prétendre reproduire l'implantation.

Quand un IFC porte sa géométrie, on pourra dessiner les vraies emprises à la
place de cette grille ; l'interface d'affichage, elle, ne changera pas.
"""

import math

_COLS_MAX = 4
_CELL_W = 190
_CELL_H = 130
_PAD = 14


def _esc(text: str) -> str:
    """Échappe le texte pour l'insérer sans risque dans du SVG."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_svg(rooms: list[dict], findings: list[dict]) -> str | None:
    """Construit la carte SVG à partir des pièces et des constats.

    Ne renvoie rien s'il n'y a pas de pièces nommées (ex. source DXF)."""
    named = [r for r in rooms if r.get("name") and r.get("area_m2")]
    if not named:
        return None

    # Pièces en défaut, indexées par nom -> plus gros écart signalé.
    issues: dict[str, dict] = {}
    for f in findings:
        target = f.get("target")
        if target:
            prev = issues.get(target)
            if prev is None or (f.get("gap") or 0) > (prev.get("gap") or 0):
                issues[target] = f

    cols = min(_COLS_MAX, len(named))
    rows = math.ceil(len(named) / cols)
    width = cols * _CELL_W
    height = rows * _CELL_H + 34  # place pour la légende

    max_area = max(r["area_m2"] for r in named)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="system-ui, sans-serif" width="100%">'
    ]

    for i, room in enumerate(named):
        cx = (i % cols) * _CELL_W
        cy = (i // cols) * _CELL_H
        # Taille de la case proportionnelle à la racine de la surface : l'aire
        # visuelle reflète alors la surface réelle.
        scale = math.sqrt(room["area_m2"] / max_area)
        bw = (_CELL_W - 2 * _PAD) * (0.45 + 0.55 * scale)
        bh = (_CELL_H - 2 * _PAD - 16) * (0.45 + 0.55 * scale)
        bx = cx + (_CELL_W - bw) / 2
        by = cy + (_CELL_H - 16 - bh) / 2

        issue = issues.get(room["name"])
        if issue:
            fill, stroke, label_col = "#fee2e2", "#dc2626", "#b91c1c"
        else:
            fill, stroke, label_col = "#dcfce7", "#16a34a", "#15803d"

        name = _esc(room["name"])
        area = room["area_m2"]
        parts.append(
            f'<rect x="{bx:.0f}" y="{by:.0f}" width="{bw:.0f}" height="{bh:.0f}" '
            f'rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{cx + _CELL_W / 2:.0f}" y="{by + bh / 2 - 4:.0f}" '
            f'text-anchor="middle" font-size="12" font-weight="600" '
            f'fill="{label_col}">{name}</text>'
        )
        parts.append(
            f'<text x="{cx + _CELL_W / 2:.0f}" y="{by + bh / 2 + 12:.0f}" '
            f'text-anchor="middle" font-size="11" fill="{label_col}">{area} m²</text>'
        )
        if issue and issue.get("gap") is not None:
            parts.append(
                f'<text x="{cx + _CELL_W / 2:.0f}" y="{by + bh + 12:.0f}" '
                f'text-anchor="middle" font-size="10" fill="#dc2626">'
                f'manque {issue["gap"]} {_esc(issue.get("unit") or "")}</text>'
            )

    # Légende.
    ly = height - 12
    parts.append(
        f'<rect x="0" y="{ly - 9}" width="11" height="11" rx="2" fill="#dcfce7" '
        f'stroke="#16a34a"/><text x="16" y="{ly}" font-size="11" fill="#475569">'
        f'conforme</text>'
    )
    parts.append(
        f'<rect x="90" y="{ly - 9}" width="11" height="11" rx="2" fill="#fee2e2" '
        f'stroke="#dc2626"/><text x="106" y="{ly}" font-size="11" fill="#475569">'
        f'non conforme</text>'
    )
    parts.append(
        f'<text x="{width:.0f}" y="{ly}" text-anchor="end" font-size="9" '
        f'fill="#94a3b8">schéma indicatif — non à l\'échelle</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
