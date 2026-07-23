"""Carte de conformité — le plan des pièces, coloré par conformité.

Deux rendus, selon ce que porte le fichier :
- si les pièces ont une GÉOMÉTRIE (emprise réelle), on dessine le vrai plan :
  chaque pièce à sa place, à sa forme, verte si conforme, rouge sinon ;
- sinon (IFC de quantités), on retombe sur un SCHÉMA : une case par pièce,
  taille proportionnelle à la surface. Honnête : ce n'est alors pas le dessin
  réel, faute de géométrie dans le fichier.

L'interface d'affichage est la même dans les deux cas.
"""

import math

_COLS_MAX = 4
_CELL_W = 190
_CELL_H = 130
_PAD = 14
_PX_PER_M = 42  # échelle du rendu géométrique
_MARGIN = 16


def _esc(text: str) -> str:
    """Échappe le texte pour l'insérer sans risque dans du SVG."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _issues_by_name(findings: list[dict]) -> dict[str, dict]:
    """Pièces en défaut -> le constat au plus gros écart."""
    issues: dict[str, dict] = {}
    for f in findings:
        target = f.get("target")
        if target:
            prev = issues.get(target)
            if prev is None or (f.get("gap") or 0) > (prev.get("gap") or 0):
                issues[target] = f
    return issues


def _colors(is_issue: bool) -> tuple[str, str, str]:
    if is_issue:
        return "#fee2e2", "#dc2626", "#b91c1c"
    return "#dcfce7", "#16a34a", "#15803d"


def _legend(width: float, y: float) -> list[str]:
    return [
        f'<rect x="0" y="{y - 9}" width="11" height="11" rx="2" fill="#dcfce7" '
        f'stroke="#16a34a"/><text x="16" y="{y}" font-size="11" fill="#475569">'
        f'conforme</text>',
        f'<rect x="90" y="{y - 9}" width="11" height="11" rx="2" fill="#fee2e2" '
        f'stroke="#dc2626"/><text x="106" y="{y}" font-size="11" fill="#475569">'
        f'non conforme</text>',
    ]


def _build_geometric_svg(rooms: list[dict], issues: dict[str, dict]) -> str:
    """Vrai plan : chaque pièce dessinée à sa position et à sa forme réelles."""
    pts_all = [p for r in rooms for p in r["footprint"]]
    minx = min(p[0] for p in pts_all)
    maxx = max(p[0] for p in pts_all)
    miny = min(p[1] for p in pts_all)
    maxy = max(p[1] for p in pts_all)

    width = (maxx - minx) * _PX_PER_M + 2 * _MARGIN
    height = (maxy - miny) * _PX_PER_M + 2 * _MARGIN + 26  # place légende

    def tx(x: float) -> float:
        return _MARGIN + (x - minx) * _PX_PER_M

    def ty(y: float) -> float:
        # Repère plan (y vers le haut) -> SVG (y vers le bas) : on inverse.
        return _MARGIN + (maxy - y) * _PX_PER_M

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="system-ui, sans-serif" width="100%">'
    ]
    for room in rooms:
        fp = room["footprint"]
        issue = issues.get(room["name"])
        fill, stroke, label_col = _colors(issue is not None)
        poly = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in fp)
        cx = sum(tx(x) for x, _ in fp) / len(fp)
        cy = sum(ty(y) for _, y in fp) / len(fp)
        parts.append(
            f'<polygon points="{poly}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{cx:.0f}" y="{cy - 4:.0f}" text-anchor="middle" '
            f'font-size="12" font-weight="600" fill="{label_col}">'
            f'{_esc(room["name"])}</text>'
        )
        parts.append(
            f'<text x="{cx:.0f}" y="{cy + 11:.0f}" text-anchor="middle" '
            f'font-size="10" fill="{label_col}">{room["area_m2"]} m²</text>'
        )
        if issue and issue.get("gap") is not None:
            parts.append(
                f'<text x="{cx:.0f}" y="{cy + 24:.0f}" text-anchor="middle" '
                f'font-size="9" fill="#dc2626">manque {issue["gap"]} '
                f'{_esc(issue.get("unit") or "")}</text>'
            )
    parts.extend(_legend(width, height - 12))
    parts.append("</svg>")
    return "".join(parts)


def _build_grid_svg(rooms: list[dict], issues: dict[str, dict]) -> str:
    """Schéma de repli : une case par pièce, faute de géométrie."""
    cols = min(_COLS_MAX, len(rooms))
    row_count = math.ceil(len(rooms) / cols)
    width = cols * _CELL_W
    height = row_count * _CELL_H + 34
    max_area = max(r["area_m2"] for r in rooms)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="system-ui, sans-serif" width="100%">'
    ]
    for i, room in enumerate(rooms):
        cx = (i % cols) * _CELL_W
        cy = (i // cols) * _CELL_H
        scale = math.sqrt(room["area_m2"] / max_area)
        bw = (_CELL_W - 2 * _PAD) * (0.45 + 0.55 * scale)
        bh = (_CELL_H - 2 * _PAD - 16) * (0.45 + 0.55 * scale)
        bx = cx + (_CELL_W - bw) / 2
        by = cy + (_CELL_H - 16 - bh) / 2
        issue = issues.get(room["name"])
        fill, stroke, label_col = _colors(issue is not None)
        parts.append(
            f'<rect x="{bx:.0f}" y="{by:.0f}" width="{bw:.0f}" height="{bh:.0f}" '
            f'rx="4" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{cx + _CELL_W / 2:.0f}" y="{by + bh / 2 - 4:.0f}" '
            f'text-anchor="middle" font-size="12" font-weight="600" '
            f'fill="{label_col}">{_esc(room["name"])}</text>'
        )
        parts.append(
            f'<text x="{cx + _CELL_W / 2:.0f}" y="{by + bh / 2 + 12:.0f}" '
            f'text-anchor="middle" font-size="11" fill="{label_col}">'
            f'{room["area_m2"]} m²</text>'
        )
        if issue and issue.get("gap") is not None:
            parts.append(
                f'<text x="{cx + _CELL_W / 2:.0f}" y="{by + bh + 12:.0f}" '
                f'text-anchor="middle" font-size="10" fill="#dc2626">'
                f'manque {issue["gap"]} {_esc(issue.get("unit") or "")}</text>'
            )
    parts.extend(_legend(width, height - 12))
    parts.append(
        f'<text x="{width}" y="{height - 12}" text-anchor="end" font-size="9" '
        f'fill="#94a3b8">schéma indicatif — non à l\'échelle</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def build_svg(rooms: list[dict], findings: list[dict]) -> str | None:
    """Choisit le vrai plan si la géométrie est là, sinon le schéma."""
    named = [r for r in rooms if r.get("name") and r.get("area_m2")]
    if not named:
        return None
    issues = _issues_by_name(findings)
    if all(r.get("footprint") for r in named):
        return _build_geometric_svg(named, issues)
    return _build_grid_svg(named, issues)
