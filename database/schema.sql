-- =========================================================
-- ArchGuard AI — Schéma MVP
-- À exécuter dans le SQL Editor de Supabase.
--
-- Note : la table des identifiants (email / mot de passe) n'est pas
-- créée ici — Supabase Auth gère déjà auth.users. On crée à la place
-- une table `profiles` reliée 1:1 à auth.users.
-- =========================================================

-- ---------------------------------------------------------
-- 1) PROFILES
-- ---------------------------------------------------------
create table if not exists public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  first_name  text,
  last_name   text,
  avatar_url  text,
  country     text,
  created_at  timestamptz not null default now()
);

-- Crée automatiquement un profil à chaque inscription
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, first_name, last_name)
  values (
    new.id,
    new.raw_user_meta_data ->> 'first_name',
    new.raw_user_meta_data ->> 'last_name'
  );
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------
-- 2) PROJECTS
-- Au MVP un projet appartient directement à un utilisateur.
-- Le rattachement à un cabinet (company_id) viendra plus tard.
-- ---------------------------------------------------------
create table if not exists public.projects (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid not null references public.profiles(id) on delete cascade,
  name          text not null,
  description   text,
  project_type  text,
  location      text,
  status        text not null default 'active',
  created_at    timestamptz not null default now()
);

create index if not exists projects_owner_id_idx on public.projects(owner_id);

-- ---------------------------------------------------------
-- 3) DOCUMENTS
-- On ne stocke que l'URL du fichier (Supabase Storage), jamais le binaire.
-- ---------------------------------------------------------
create table if not exists public.documents (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references public.projects(id) on delete cascade,
  uploaded_by  uuid not null references public.profiles(id),
  name         text not null,
  file_type    text,
  storage_path text not null,
  created_at   timestamptz not null default now()
);

create index if not exists documents_project_id_idx on public.documents(project_id);

-- ---------------------------------------------------------
-- 4) AI_ANALYSES
-- result en JSONB : le format de sortie de l'IA évoluera sans migration.
-- ---------------------------------------------------------
create table if not exists public.ai_analyses (
  id            uuid primary key default gen_random_uuid(),
  document_id   uuid not null references public.documents(id) on delete cascade,
  model_version text,
  score         integer check (score between 0 and 100),
  status        text not null default 'pending',  -- pending | done | failed
  error_message text,
  result        jsonb,
  created_at    timestamptz not null default now()
);

create index if not exists ai_analyses_document_id_idx on public.ai_analyses(document_id);

-- =========================================================
-- ROW LEVEL SECURITY
-- Sans ces règles, tout utilisateur connecté peut lire les
-- données de tous les autres. À activer dès le départ.
-- =========================================================

alter table public.profiles    enable row level security;
alter table public.projects    enable row level security;
alter table public.documents   enable row level security;
alter table public.ai_analyses enable row level security;

drop policy if exists "own profile" on public.profiles;
create policy "own profile" on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists "own projects" on public.projects;
create policy "own projects" on public.projects
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

drop policy if exists "docs of own projects" on public.documents;
create policy "docs of own projects" on public.documents
  for all using (
    exists (
      select 1 from public.projects p
      where p.id = documents.project_id and p.owner_id = auth.uid()
    )
  );

drop policy if exists "analyses of own docs" on public.ai_analyses;
create policy "analyses of own docs" on public.ai_analyses
  for all using (
    exists (
      select 1 from public.documents d
      join public.projects p on p.id = d.project_id
      where d.id = ai_analyses.document_id and p.owner_id = auth.uid()
    )
  );

-- =========================================================
-- STORAGE
-- Bucket privé pour les plans. Chaque fichier est rangé sous
-- <user_id>/<project_id>/<fichier>, ce qui permet de filtrer
-- l'accès sur le premier segment du chemin.
-- =========================================================

insert into storage.buckets (id, name, public)
values ('plans', 'plans', false)
on conflict (id) do nothing;

drop policy if exists "own plans read" on storage.objects;
create policy "own plans read" on storage.objects
  for select using (
    bucket_id = 'plans' and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "own plans write" on storage.objects;
create policy "own plans write" on storage.objects
  for insert with check (
    bucket_id = 'plans' and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "own plans delete" on storage.objects;
create policy "own plans delete" on storage.objects
  for delete using (
    bucket_id = 'plans' and (storage.foldername(name))[1] = auth.uid()::text
  );
