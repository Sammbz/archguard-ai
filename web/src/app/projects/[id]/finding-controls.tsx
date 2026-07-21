'use client'

import { useState, useTransition } from 'react'
import { setFindingStatus } from '../actions'
import type { FindingStatusValue } from '@/lib/types'

const OPTIONS: { value: FindingStatusValue; label: string; active: string }[] = [
  { value: 'open', label: 'Ouvert', active: 'bg-slate-700 text-white' },
  { value: 'fixed', label: 'Corrigé', active: 'bg-amber-500 text-white' },
  { value: 'verified', label: 'Vérifié', active: 'bg-emerald-600 text-white' },
  { value: 'dismissed', label: 'Écarté', active: 'bg-slate-400 text-white' },
]

export function FindingControls({
  projectId,
  analysisId,
  findingIndex,
  current,
}: {
  projectId: string
  analysisId: string
  findingIndex: number
  current: FindingStatusValue | undefined
}) {
  const [status, setStatus] = useState<FindingStatusValue>(current ?? 'open')
  const [pending, startTransition] = useTransition()

  function update(next: FindingStatusValue) {
    if (next === status) return
    setStatus(next) // optimiste : l'UI réagit avant l'aller-retour serveur
    startTransition(() =>
      setFindingStatus(projectId, analysisId, findingIndex, next)
    )
  }

  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          disabled={pending}
          onClick={() => update(opt.value)}
          className={`rounded px-2 py-0.5 text-xs font-medium transition disabled:opacity-50 ${
            status === opt.value
              ? opt.active
              : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
