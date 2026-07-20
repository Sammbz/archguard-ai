"""Service d'analyse IA d'ArchGuard.

Flux : le front envoie un document_id -> on télécharge le plan depuis
Supabase Storage -> on l'envoie au modèle vision -> on écrit le résultat
dans la table ai_analyses.

L'appel est synchrone : l'utilisateur attend le résultat (10-30 s). Voir
le README pour le passage en asynchrone quand le volume l'exigera.
"""

import base64
import json
import os

import fitz  # PyMuPDF
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel
from supabase import create_client

from prompt import MODEL, SYSTEM_PROMPT

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "plans")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

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


def to_png_bytes(raw: bytes, file_type: str | None) -> bytes:
    """Le modèle vision ne lit que des images : on rend la 1re page des PDF."""
    if (file_type or "").lower() != "pdf":
        return raw
    with fitz.open(stream=raw, filetype="pdf") as doc:
        if doc.page_count == 0:
            raise HTTPException(400, "PDF vide")
        # zoom x2 : un plan comporte des annotations fines, la résolution
        # native rend souvent les cotes illisibles pour le modèle.
        pixmap = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2))
        return pixmap.tobytes("png")


def run_model(png: bytes) -> dict:
    data_url = "data:image/png;base64," + base64.b64encode(png).decode()
    response = openai_client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": data_url}}],
            },
        ],
    )
    return json.loads(response.choices[0].message.content)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    documents = (
        supabase.table("documents")
        .select("id, storage_path, file_type")
        .eq("id", req.document_id)
        .execute()
        .data
    )
    if not documents:
        raise HTTPException(404, "Document introuvable")
    document = documents[0]

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
        result = run_model(to_png_bytes(raw, document.get("file_type")))
        score = int(result.get("score", 0))
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
