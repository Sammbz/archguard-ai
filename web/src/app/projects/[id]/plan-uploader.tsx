'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const AI_SERVICE_URL =
  process.env.NEXT_PUBLIC_AI_SERVICE_URL ?? 'http://localhost:8000'

export function PlanUploader({ projectId }: { projectId: string }) {
  const router = useRouter()
  const supabase = createClient()

  const [step, setStep] = useState<'idle' | 'uploading' | 'analyzing'>('idle')
  const [error, setError] = useState<string | null>(null)

  async function handleFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return

    setError(null)
    setStep('uploading')

    try {
      const {
        data: { user },
      } = await supabase.auth.getUser()
      if (!user) throw new Error('Session expirée, reconnectez-vous.')

      // Le premier segment du chemin doit être l'id utilisateur :
      // les policies du bucket filtrent dessus.
      const path = `${user.id}/${projectId}/${crypto.randomUUID()}-${file.name}`

      const { error: uploadError } = await supabase.storage
        .from('plans')
        .upload(path, file)
      if (uploadError) throw new Error(uploadError.message)

      const { data: document, error: insertError } = await supabase
        .from('documents')
        .insert({
          project_id: projectId,
          uploaded_by: user.id,
          name: file.name,
          file_type: file.name.split('.').pop()?.toLowerCase() ?? null,
          storage_path: path,
        })
        .select('id')
        .single()
      if (insertError) throw new Error(insertError.message)

      setStep('analyzing')
      const response = await fetch(`${AI_SERVICE_URL}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document_id: document.id }),
      })
      if (!response.ok) {
        throw new Error(
          "Le plan est enregistré mais l'analyse a échoué. Vérifiez que le service IA tourne."
        )
      }

      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur inattendue')
    } finally {
      setStep('idle')
      event.target.value = ''
    }
  }

  const busy = step !== 'idle'

  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-5">
      <label className="flex cursor-pointer flex-col items-start gap-2">
        <span className="text-sm font-medium">Téléverser un plan</span>
        <span className="text-sm text-slate-500">
          PDF, PNG, JPG ou DXF (AutoCAD). Le DXF est mesuré au réel ; les autres
          formats sont analysés visuellement. Pour un fichier .dwg, exportez-le
          d&apos;abord en .dxf. L&apos;analyse démarre automatiquement et prend
          10 à 30 secondes.
        </span>
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.dxf"
          disabled={busy}
          onChange={handleFile}
          className="mt-1 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-slate-800 disabled:opacity-50"
        />
      </label>

      {step === 'uploading' && (
        <p className="mt-3 text-sm text-slate-500">Téléversement…</p>
      )}
      {step === 'analyzing' && (
        <p className="mt-3 text-sm text-slate-500">Analyse IA en cours…</p>
      )}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </div>
  )
}
