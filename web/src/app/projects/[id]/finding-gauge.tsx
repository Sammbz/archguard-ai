import type { AnalysisIssue } from '@/lib/types'

/** Visualise l'écart d'un constat : barre remplie jusqu'à la valeur mesurée,
 *  la part manquante (jusqu'au seuil) en rouge hachuré. On montre DE COMBIEN
 *  c'est hors norme — sans concevoir la correction, qui reste à l'architecte. */
export function FindingGauge({ issue }: { issue: AnalysisIssue }) {
  const { measured, threshold, gap, unit } = issue
  if (
    measured == null ||
    threshold == null ||
    gap == null ||
    threshold <= 0
  ) {
    return null
  }

  // Le seuil = 100 % de la barre ; la mesure occupe sa fraction.
  const filledPct = Math.max(0, Math.min(100, (measured / threshold) * 100))

  return (
    <div className="mt-2 max-w-md">
      <div className="flex h-5 w-full overflow-hidden rounded bg-red-100">
        <div
          className="flex items-center justify-end bg-amber-400 pr-1 text-[10px] font-medium text-white"
          style={{ width: `${filledPct}%` }}
        >
          {measured}
        </div>
        <div className="flex flex-1 items-center justify-center text-[10px] font-medium text-red-700">
          manque {gap} {unit}
        </div>
      </div>
      <div className="mt-0.5 flex justify-between text-[10px] text-slate-400">
        <span>mesuré : {measured} {unit}</span>
        <span>minimum requis : {threshold} {unit}</span>
      </div>
    </div>
  )
}
