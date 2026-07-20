# ArchGuard AI

SaaS d'analyse de plans d'architecture par IA. Un architecte téléverse un plan,
l'IA renvoie un score de qualité, la liste des problèmes détectés et des
recommandations.

Ce dépôt contient le **MVP** : le périmètre minimal qui prouve la valeur du
produit. La facturation, le multi-cabinets, les rôles fins, les versions de
documents, les commentaires et les tâches sont volontairement hors périmètre
(voir « Après le MVP »).

## Structure

```
archguard-ai/
├── database/schema.sql   Schéma PostgreSQL + policies RLS (à exécuter dans Supabase)
├── web/                  Frontend Next.js (App Router, TypeScript, Tailwind)
└── ai-service/           Service d'analyse FastAPI (Python)
```

## Architecture

```
Next.js ──────────────► Supabase   (auth, base de données, stockage des plans)
   │
   └──── POST /analyze ─► FastAPI ──► modèle vision OpenAI
                             │
                             └──► écrit le résultat dans ai_analyses
```

Le métier passe directement par Supabase (les API CRUD sont générées
automatiquement et protégées par les policies RLS). Le seul service applicatif
à héberger est `ai-service`, isolé parce que l'IA a des contraintes propres :
Python, traitements longs, coût à l'appel, remplacement probable par un modèle
spécialisé plus tard.

## Démarrage

### 1. Base de données

Créer un projet sur [supabase.com](https://supabase.com), puis coller le contenu
de `database/schema.sql` dans le **SQL Editor** et l'exécuter. Cela crée les
quatre tables, les policies RLS et le bucket de stockage `plans`.

### 2. Frontend

```bash
cd web
cp .env.local.example .env.local   # puis remplir les valeurs
npm install
npm run dev                        # http://localhost:3000
```

Les clés se trouvent dans Supabase sous **Project Settings > API**.

### 3. Service IA

```bash
cd ai-service
python -m venv .venv
.venv\Scripts\activate             # Windows  (source .venv/bin/activate ailleurs)
pip install -r requirements.txt
cp .env.example .env               # puis remplir les valeurs
uvicorn main:app --reload --port 8000
```

## Sécurité

- La clé `SUPABASE_SERVICE_ROLE_KEY` **contourne les policies RLS**. Elle ne doit
  exister que dans `ai-service/.env`, jamais dans le frontend ni dans le dépôt.
- Le frontend n'utilise que la clé anonyme ; c'est le RLS qui garantit qu'un
  utilisateur ne voit que ses propres données.
- Le bucket `plans` est privé. Les fichiers sont rangés sous
  `<user_id>/<project_id>/<fichier>`, et les policies filtrent sur le premier
  segment du chemin.

## Limite à connaître

L'analyse est produite par un modèle de langage multimodal généraliste. Elle
constitue une **aide à la décision**, pas une validation de conformité
réglementaire. L'interface doit le dire explicitement à l'utilisateur — c'est un
enjeu juridique réel dans le bâtiment.

## Après le MVP

Dans l'ordre, une fois que l'analyse IA a trouvé son public :

1. Multi-cabinets (`companies`, `company_members`, `roles`) et RLS par cabinet
2. Facturation via Stripe — la base ne stocke que les références
   (`stripe_customer_id`, `stripe_subscription_id`), Stripe reste la source de vérité
3. Versions de documents, avec l'analyse IA rattachée à `document_versions.id`
   et non à `documents.id`
4. Commentaires positionnés sur le plan, tâches, notifications
5. Analyse asynchrone (file d'attente) quand l'attente synchrone deviendra gênante
6. Modèle de vision spécialisé, entraîné sur de vrais plans, à la place du LLM
   généraliste
