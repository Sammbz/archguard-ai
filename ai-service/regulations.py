"""Catalogue des règles réglementaires — le socle d'ingestion d'un code.

Chaque entrée décrit UNE exigence chiffrée vérifiable sur un plan. Le moteur
(rules.py) l'évalue sans connaître le pays : ajouter le Code sénégalais revient
à ajouter des entrées ici, avec le bon seuil, l'article, et validated=True —
sans toucher au moteur.

⚠️ Règle d'or produit : tant que `validated` est False, le seuil est un simple
repère (valeur courante), PAS du droit. Le constat correspondant est alors
présenté comme « point d'attention à valider », jamais comme une non-conformité
réglementaire. On ne passe `validated=True` et on ne renseigne `code_reference`
qu'après vérification humaine (architecte) sur le texte officiel.

Types de contrôle (`kind`) reconnus par le moteur :
- "min_room_area"  : surface d'un espace fermé < seuil (en m²)
- "min_dimension"  : une cote < seuil (en m)
"""

from dataclasses import dataclass

GENERIC = "GENERIC"  # repères par défaut, non rattachés à un pays


@dataclass(frozen=True)
class Regulation:
    id: str
    axis: str          # accessibility|safety|lighting|dimensions|circulation
    kind: str          # voir en-tête
    threshold: float   # en unité métrique de base (m ou m²)
    severity: str      # low|medium|high
    label: str         # intitulé lisible de l'exigence
    country: str = GENERIC
    code_reference: str | None = None  # ex. "Code construction SN, art. R.xx"
    validated: bool = False            # True seulement après contrôle humain


# --- Repères génériques (valeurs courantes, à remplacer par pays) ----------
CATALOG: list[Regulation] = [
    Regulation(
        id="room_min_area",
        axis="dimensions",
        kind="min_room_area",
        threshold=9.0,
        severity="medium",
        label="Surface minimale d'une pièce principale",
    ),
    Regulation(
        id="passage_min_width",
        axis="circulation",
        kind="min_dimension",
        threshold=0.90,
        severity="high",
        label="Largeur minimale de passage / circulation",
    ),
    # --- Sénégal : à remplir après validation architecte sur le texte -------
    # Modèle : dès qu'une valeur est confirmée, dupliquer une entrée ci-dessus
    # avec country="SN", le seuil réel, code_reference renseigné, validated=True.
    # Regulation(id="sn_ceiling_min_height", axis="dimensions",
    #     kind="min_dimension", threshold=2.50, severity="medium",
    #     label="Hauteur sous plafond minimale",
    #     country="SN", code_reference="Code construction SN, art. R.xx",
    #     validated=True),
]


def for_country(country: str) -> list[Regulation]:
    """Règles applicables : celles du pays + les repères génériques en secours."""
    generic = [r for r in CATALOG if r.country == GENERIC]
    if country == GENERIC:
        return generic
    specific = [r for r in CATALOG if r.country == country]
    return specific + generic
