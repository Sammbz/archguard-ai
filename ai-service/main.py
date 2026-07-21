"""Service d'analyse IA d'ArchGuard.

Flux : le front envoie un document_id -> on télécharge le plan depuis
Supabase Storage -> on l'analyse -> on écrit le résultat dans ai_analyses.

Deux voies d'analyse selon le format du fichier :
- Image (PDF, PNG, JPG) : on rend les pages et le modèle « regarde » (VISION).
  Le PDF est traité en entier, page par page, pas seulement la première.
- Vecteur (DXF) : on extrait les mesures EXACTES du fichier CAO et on les
  fournit au modèle, qui vérifie des chiffres plutôt que d'estimer (VECTOR).

L'appel est synchrone : l'utilisateur attend le résultat (10-30 s). Voir
le README pour le passage en asynchrone quand le volume l'exigera.
"""

import base64
import json
import os

import fitz  # PyMuPDF
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel
from supabase import create_client

import regulations
from prompt import MODEL, SYSTEM_PROMPT, SYSTEM_PROMPT_VECTOR

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "plans")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

# Un dossier de permis fait plusieurs feuilles, mais chaque page est un appel
# vision payant : on borne pour garder le coût prévisible.
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "15"))

# Pays dont on applique les règles réglementaires (FR, SN, RDC, GENERIC).
# Pont temporaire : à terme, le pays viendra du projet (colonne à ajouter),
# pas d'une variable globale.
DEFAULT_COUNTRY = os.getenv("DEFAULT_COUNTRY", regulations.GENERIC)

app = FastAPI(title="ArchGuard AI — service d'analyse")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

openai_client = OpenAI()
# La clé service_role contourne les policies RLS : elle ne doit jamais
# quitter le serveur ni être exposée au navigateur.
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


class AnalyzeRequest(BaseModel):
    document_id: str


def authenticated_user_id(authorization: str | None) -> str:
    """Valide le jeton Bearer envoyé par le front auprès de Supabase Auth.

    Sans cette barrière, /analyze est ouvert à tous : la clé service_role
    contournant le RLS, n'importe qui pourrait analyser les documents d'autrui
    et brûler le budget du modèle. Le CORS ne protège pas (curl l'ignore)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Jeton d'authentification manquant")
    token = authorization.split(" ", 1)[1].strip()
    try:
        response = supabase.auth.get_user(token)
    except Exception as exc:
        raise HTTPException(401, "Jeton invalide") from exc
    if not response or not response.user:
        raise HTTPException(401, "Jeton invalide")
    return response.user.id


def pdf_to_png_pages(raw: bytes) -> list[bytes]:
    """Rend chaque page du PDF (dans la limite) en PNG pour le modèle vision."""
    pages: list[bytes] = []
    with fitz.open(stream=raw, filetype="pdf") as doc:
        if doc.page_count == 0:
            raise HTTPException(400, "PDF vide")
        for index in range(min(doc.page_count, MAX_PDF_PAGES)):
            # zoom x2 : un plan comporte des annotations fines, la résolution
            # native rend souvent les cotes illisibles pour le modèle.
            pixmap = doc.load_page(index).get_pixmap(matrix=fitz.Matrix(2, 2))
            pages.append(pixmap.tobytes("png"))
    return pages


def images_for_vision(raw: bytes, file_type: str | None) -> list[bytes]:
    """Le modèle vision ne lit que des images : PDF -> pages, sinon tel quel."""
    if (file_type or "").lower() == "pdf":
        return pdf_to_png_pages(raw)
    return [raw]


def run_vision(images: list[bytes]) -> dict:
    """Mode image : on envoie toutes les pages du dossier en une requête."""
    content: list[dict] = [
        {"type": "text", "text": f"Dossier de {len(images)} page(s) à analyser."}
    ]
    for png in images:
        data_url = "data:image/png;base64," + base64.b64encode(png).decode()
        content.append({"type": "image_url", "image_url": {"url": data_url}})

    response = openai_client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
    )
    return json.loads(response.choices[0].message.content)


def run_vector(measurements_text: str) -> dict:
    """Mode vecteur : on envoie les mesures exactes extraites du .dxf."""
    response = openai_client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_VECTOR},
            {"role": "user", "content": measurements_text},
        ],
    )
    return json.loads(response.choices[0].message.content)


def convert_dwg_to_dxf(raw: bytes, converter_path: str) -> bytes:
    """Convertit un .dwg en .dxf via ODA File Converter (moteur externe).

    L'outil opère sur des dossiers : on écrit le .dwg dans un dossier temporaire,
    on lance la conversion, on relit le .dxf produit."""
    import pathlib
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as in_dir, tempfile.TemporaryDirectory() as out_dir:
        (pathlib.Path(in_dir) / "plan.dwg").write_bytes(raw)
        try:
            # <input> <output> <version cible> <type> <récursif> <audit>
            subprocess.run(
                [converter_path, in_dir, out_dir, "ACAD2018", "DXF", "0", "1"],
                check=True,
                timeout=120,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(502, f"Conversion .dwg échouée : {exc}") from exc

        produced = list(pathlib.Path(out_dir).glob("*.dxf"))
        if not produced:
            raise HTTPException(502, "Conversion .dwg -> .dxf : aucun fichier produit.")
        return produced[0].read_bytes()


def analyze_document(raw: bytes, file_type: str | None) -> dict:
    """Aiguille vers la voie vecteur (.dxf) ou image selon le format."""
    ft = (file_type or "").lower()

    if ft == "dwg":
        # Le .dwg natif est binaire et propriétaire. La conversion en .dxf exige
        # un moteur externe (ODA File Converter). Point d'intégration : si son
        # chemin est fourni via DWG_TO_DXF_CONVERTER, on convertit puis on
        # bascule en voie vectorielle ; sinon on demande un export manuel.
        converter = os.getenv("DWG_TO_DXF_CONVERTER")
        if converter:
            raw = convert_dwg_to_dxf(raw, converter)
            ft = "dxf"
        else:
            raise HTTPException(
                400,
                "Format .dwg non lu directement. Exporte en .dxf (analyse "
                "vectorielle précise) ou en PDF (analyse visuelle) depuis ton "
                "logiciel de CAO.",
            )

    if ft == "dxf":
        # Import paresseux : la voie image ne doit pas dépendre de la lib CAO.
        try:
            import dxf_reader
            import rules
        except ImportError as exc:
            raise HTTPException(
                503, "Lecture .dxf indisponible (dépendance ezdxf manquante)."
            ) from exc

        measurements = dxf_reader.extract_measurements(raw)

        # 1) Constats DÉTERMINISTES : calculés en dur, certains, chiffrés.
        certain = rules.evaluate(measurements, DEFAULT_COUNTRY)
        # 2) Analyse IA par-dessus, pour le contexte et les axes non mesurables.
        result = run_vector(dxf_reader.to_prompt_text(measurements))

        # Les constats certains passent devant ceux estimés par le modèle.
        result["errors"] = certain + (result.get("errors") or [])
        return result

    return run_vision(images_for_vision(raw, ft))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest, authorization: str | None = Header(default=None)):
    user_id = authenticated_user_id(authorization)

    documents = (
        supabase.table("documents")
        .select("id, storage_path, file_type, projects(owner_id)")
        .eq("id", req.document_id)
        .execute()
        .data
    )
    if not documents:
        raise HTTPException(404, "Document introuvable")
    document = documents[0]

    # Le document doit appartenir à l'utilisateur authentifié. On revérifie
    # l'appartenance ici parce que la clé service_role ignore le RLS.
    project = document.get("projects")
    if isinstance(project, list):
        project = project[0] if project else None
    owner_id = project.get("owner_id") if project else None
    if owner_id != user_id:
        raise HTTPException(403, "Accès refusé à ce document")

    analysis_id = (
        supabase.table("ai_analyses")
        .insert({
            "document_id": document["id"],
            "model_version": MODEL,
            "status": "pending",
        })
        .execute()
        .data[0]["id"]
    )

    try:
        raw = supabase.storage.from_(STORAGE_BUCKET).download(document["storage_path"])
        result = analyze_document(raw, document.get("file_type"))
        score = int(result.get("score", 0))
    except HTTPException:
        # Erreur métier explicite (format non géré, PDF vide…) : on la remonte
        # telle quelle après avoir marqué l'analyse en échec.
        supabase.table("ai_analyses").update(
            {"status": "failed", "error_message": "format ou contenu non exploitable"}
        ).eq("id", analysis_id).execute()
        raise
    except Exception as exc:
        # On enregistre l'échec plutôt que de laisser la ligne en "pending"
        # indéfiniment : le front doit pouvoir afficher une erreur.
        supabase.table("ai_analyses").update(
            {"status": "failed", "error_message": str(exc)[:500]}
        ).eq("id", analysis_id).execute()
        raise HTTPException(502, f"Analyse impossible : {exc}") from exc

    supabase.table("ai_analyses").update(
        {"status": "done", "score": score, "result": result}
    ).eq("id", analysis_id).execute()

    return {"analysis_id": analysis_id, "status": "done", "score": score}
