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
    concern: str       # sujet traité, ex. "surface_piece" — sert au dédoublonnage
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
        concern="surface_piece",
        threshold=9.0,
        severity="medium",
        label="Surface minimale d'une pièce principale",
    ),
    Regulation(
        id="passage_min_width",
        axis="circulation",
        kind="min_dimension",
        concern="largeur_circulation",
        threshold=0.90,
        severity="high",
        label="Largeur minimale de passage / circulation",
    ),
    # --- France : valeurs sourcées (Légifrance) ----------------------------
    # ⚠️ Le moteur applique ces règles SANS distinguer le type de bâtiment ni la
    # nature de l'élément (une cote de 0,85 m sera signalée qu'elle soit une
    # porte, un mur ou un meuble). La portée exacte (ERP vs logement, neuf vs
    # existant) suppose la sémantique des entités, encore à faire. À utiliser en
    # connaissance de cause.
    Regulation(
        id="fr_room_min_area",
        axis="dimensions",
        kind="min_room_area",
        concern="surface_piece",
        threshold=9.0,
        severity="medium",
        label="Surface habitable minimale d'une pièce principale (logement décent)",
        country="FR",
        code_reference="FR, décret n°2002-120 du 30/01/2002, art. 4",
        validated=True,
    ),
    Regulation(
        id="fr_ceiling_min_height",
        axis="dimensions",
        kind="min_ceiling_height",  # dormant : pas de hauteur sur un plan 2D
        concern="hauteur_plafond",
        threshold=2.20,
        severity="medium",
        label="Hauteur sous plafond minimale (logement décent)",
        country="FR",
        code_reference="FR, décret n°2002-120 du 30/01/2002, art. 4",
        validated=True,
    ),
    Regulation(
        id="fr_door_min_width",
        axis="accessibility",
        kind="min_dimension",
        concern="largeur_porte",
        threshold=0.90,
        severity="high",
        label="Largeur minimale d'une porte intérieure (accessibilité)",
        country="FR",
        code_reference="FR, arrêté du 1er août 2006 (portes intérieures)",
        validated=True,
    ),

    # --- Sénégal : à remplir après validation architecte sur le texte -------
    # Le texte réglementaire est scanné/bloqué : valeurs à obtenir via un
    # architecte. Modèle d'entrée validée : voir le bloc France ci-dessus, avec
    # country="SN" et l'article du Code de la construction sénégalais.

    # --- RDC : cadre légal identifié, seuils non digitalisés ----------------
    # Décret de 1957 sur l'urbanisme + arrêté n°CAB/MIN 007/2013 (permis de
    # bâtir) + nouveau code en cours de validation (urbanisme.gouv.cd). Aucun
    # seuil dimensionnel numérique exploitable trouvé en ligne : à obtenir sur
    # le texte officiel avant toute entrée validée.
]


def for_country(country: str) -> list[Regulation]:
    """Règles applicables : celles du pays, complétées par les repères génériques
    sur les seuls sujets que le pays ne couvre pas (pas de doublon)."""
    generic = [r for r in CATALOG if r.country == GENERIC]
    if country == GENERIC:
        return generic
    specific = [r for r in CATALOG if r.country == country]
    covered = {r.concern for r in specific}
    fallback = [r for r in generic if r.concern not in covered]
    return specific + fallback
