import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'
import type { Project } from '@/lib/types'
import { createProject, signOut } from './actions'

export default async function ProjectsPage() {
  const supabase = await createClient()
  const { data: projects } = await supabase
    .from('projects')
    .select('*')
    .order('created_at', { ascending: false })

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Mes projets</h1>
        <form action={signOut}>
          <button className="text-sm text-slate-500 hover:text-slate-900">
            Se déconnecter
          </button>
        </form>
      </header>

      <form
        action={createProject}
        className="mt-6 space-y-3 rounded-xl border border-slate-200 bg-white p-5"
      >
        <p className="text-sm font-medium">Nouveau projet</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <input
            name="name"
            required
            placeholder="Nom du projet"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
          />
          <input
            name="location"
            placeholder="Localisation"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
          />
          <input
            name="project_type"
            placeholder="Type (résidentiel, commercial…)"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
          />
          <input
            name="description"
            placeholder="Description"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
          />
        </div>
        <button className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800">
          Créer le projet
        </button>
      </form>

      <ul className="mt-6 space-y-2">
        {(projects as Project[] | null)?.map((project) => (
          <li key={project.id}>
            <Link
              href={`/projects/${project.id}`}
              className="block rounded-xl border border-slate-200 bg-white p-4 hover:border-slate-400"
            >
              <p className="font-medium">{project.name}</p>
              <p className="mt-0.5 text-sm text-slate-500">
                {[project.project_type, project.location]
                  .filter(Boolean)
                  .join(' · ') || 'Aucun détail'}
              </p>
            </Link>
          </li>
        ))}
      </ul>

      {projects?.length === 0 && (
        <p className="mt-6 text-sm text-slate-500">
          Aucun projet pour l&apos;instant. Créez-en un ci-dessus.
        </p>
      )}
    </main>
  )
}
