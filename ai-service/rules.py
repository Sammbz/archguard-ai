"""Moteur de règles déterministe — cœur du « Niveau 3 ».

Ici, pas d'IA : on compare des mesures EXACTES (issues du .dxf) à des seuils.
Chaque constat produit est certain, chiffré, et porte un emplacement pour
l'article de code correspondant (`code_reference`).

⚠️ Les seuils ci-dessous sont PROVISOIRES — des valeurs courantes, pas le droit
d'un pays donné. Ils doivent être remplacés, un par un, par les valeurs du Code
de la construction ciblé (Sénégal en premier), et `code_reference` renseigné.
Tant que `code_reference` vaut None, le constat est présenté comme un point
d'attention, jamais comme une non-conformité réglementaire.
"""

from dataclasses import dataclass

# --- Seuils PROVISOIRES (à remplacer par le code local) -------------------
MIN_ROOM_AREA_M2 = 9.0        # surface plancher mini d'une pièce principale
MIN_PASSAGE_M = 0.90          # largeur de passage / circulation
MAX_PLAUSIBLE_ROOM_M2 = 60.0  # au-delà, sans doute pas une pièce isolée


@dataclass
class Finding:
    """Un constat déterministe. `type`/`severity`/`description` sont lus tels
    quels par le front ; les autres champs enrichissent le JSONB stocké."""

    type: str
    severity: str
    description: str
    measured: float | None = None
    threshold: float | None = None
    code_reference: str | None = None  # ex. "Code construction SN, art. R.xxx"

    def as_dict(self) -> dict:
        return {
            "type": self.type,
            "severity": self.severity,
            "description": self.description,
            "measured": self.measured,
            "threshold": self.threshold,
            "code_reference": self.code_reference,
            "certain": True,  # distingue du constat estimé par l'IA
        }


def evaluate(measurements: dict) -> list[dict]:
    """Applique les règles aux mesures extraites. Retourne des constats certains.

    N'émet un constat que lorsque la mesure est fiable ET que l'unité est connue
    (sinon on ne peut pas comparer à un seuil en mètres)."""
    findings: list[Finding] = []
    unit_known = measurements.get("to_meter_factor") is not None

    # --- Règle 1 : surface des pièces --------------------------------------
    # Une polyligne fermée de surface plausible sous le minimum courant.
    if unit_known:
        for area in measurements.get("room_areas_m2", []):
            if area < MIN_ROOM_AREA_M2:
                findings.append(
                    Finding(
                        type="dimensions",
                        severity="medium",
                        description=(
                            f"Espace fermé de {area} m², sous le minimum courant de "
                            f"{MIN_ROOM_AREA_M2} m² pour une pièce principale "
                            f"(à confirmer : nature de l'espace)."
                        ),
                        measured=area,
                        threshold=MIN_ROOM_AREA_M2,
                    )
                )

    # --- Règle 2 : largeur de passage --------------------------------------
    # Toute cote inférieure au minimum de circulation est signalée.
    if unit_known:
        factor = measurements["to_meter_factor"]
        for dim in measurements.get("dimensions", []):
            dim_m = dim * factor
            if 0 < dim_m < MIN_PASSAGE_M:
                findings.append(
                    Finding(
                        type="circulation",
                        severity="high",
                        description=(
                            f"Cote de {round(dim_m, 2)} m relevée, inférieure au "
                            f"minimum courant de {MIN_PASSAGE_M} m pour un passage "
                            f"(à confirmer : s'agit-il bien d'une circulation ?)."
                        ),
                        measured=round(dim_m, 2),
                        threshold=MIN_PASSAGE_M,
                    )
                )

    return [f.as_dict() for f in findings]
