import Link from 'next/link'
import { notFound } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import type { AnalysisIssue, PlanDocument, Project } from '@/lib/types'
import { PlanUploader } from './plan-uploader'

const SEVERITY_STYLES: Record<AnalysisIssue['severity'], string> = {
  high: 'bg-red-50 text-red-700',
  medium: 'bg-amber-50 text-amber-700',
  low: 'bg-slate-100 text-slate-600',
}

function scoreColor(score: number) {
  if (score >= 80) return 'text-emerald-600'
  if (score >= 50) return 'text-amber-600'
  return 'text-red-600'
}

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  // `params` est une promesse depuis Next.js 16.
  const { id } = await params
  const supabase = await createClient()

  const { data: project } = await supabase
    .from('projects')
    .select('*')
    .eq('id', id)
    .maybeSingle()

  if (!project) notFound()

  const { data: documents } = await supabase
    .from('documents')
    .select('*, ai_analyses(*)')
    .eq('project_id', id)
    .order('created_at', { ascending: false })

  const typedProject = project as Project

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 p-6">
      <Link href="/projects" className="text-sm text-slate-500 hover:text-slate-900">
        ← Mes projets
      </Link>

      <h1 className="mt-3 text-xl font-semibold tracking-tight">
        {typedProject.name}
      </h1>
      <p className="mt-0.5 text-sm text-slate-500">
        {[typedProject.project_type, typedProject.location]
          .filter(Boolean)
          .join(' · ') || 'Aucun détail'}
      </p>

      <div className="mt-6">
        <PlanUploader projectId={id} />
      </div>

      <div className="mt-6 space-y-4">
        {(documents as PlanDocument[] | null)?.map((document) => {
          // Une analyse par téléversement, la plus récente d'abord.
          const analysis = [...(document.ai_analyses ?? [])].sort((a, b) =>
            b.created_at.localeCompare(a.created_at)
          )[0]

          return (
            <article
              key={document.id}
              className="rounded-xl border border-slate-200 bg-white p-5"
            >
              <div className="flex items-baseline justify-between gap-4">
                <p className="font-medium break-all">{document.name}</p>
                {analysis?.status === 'done' && analysis.score !== null && (
                  <p className={`text-2xl font-semibold ${scoreColor(analysis.score)}`}>
                    {analysis.score}
                    <span className="text-sm text-slate-400">/100</span>
                  </p>
                )}
              </div>

              {!analysis && (
                <p className="mt-2 text-sm text-slate-500">Aucune analyse.</p>
              )}
              {analysis?.status === 'pending' && (
                <p className="mt-2 text-sm text-slate-500">Analyse en cours…</p>
              )}
              {analysis?.status === 'failed' && (
                <p className="mt-2 text-sm text-red-600">
                  Analyse échouée : {analysis.error_message}
                </p>
              )}

              {analysis?.status === 'done' && analysis.result && (
                <div className="mt-3 space-y-4">
                  {analysis.result.summary && (
                    <p className="text-sm text-slate-600">
                      {analysis.result.summary}
                    </p>
                  )}

                  {!!analysis.result.errors?.length && (
                    <div>
                      <p className="text-sm font-medium">Problèmes détectés</p>
                      <ul className="mt-2 space-y-2">
                        {analysis.result.errors.map((issue, index) => (
                          <li key={index} className="flex gap-2 text-sm">
                            <span
                              className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${
                                SEVERITY_STYLES[issue.severity] ??
                                SEVERITY_STYLES.low
                              }`}
                            >
                              {issue.type}
                            </span>
                            <span className="text-slate-600">
                              {issue.description}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {!!analysis.result.suggestions?.length && (
                    <div>
                      <p className="text-sm font-medium">Recommandations</p>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
                        {analysis.result.suggestions.map((suggestion, index) => (
                          <li key={index}>{suggestion}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <p className="text-xs text-slate-400">
                    Analyse générée par IA — aide à la décision, ne vaut pas
                    validation de conformité réglementaire.
                  </p>
                </div>
              )}
            </article>
          )
        })}
      </div>
    </main>
  )
}
