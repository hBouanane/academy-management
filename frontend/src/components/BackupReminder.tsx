import { useEffect, useState } from "react"
import { ShieldAlert } from "lucide-react"

import { apiGet } from "@/lib/api"
import type { BackupState } from "@/lib/api"

/**
 * Le rappel qui vaut mieux qu'une discipline.
 *
 * Emporter ses sauvegardes est un geste qu'on remet toujours à demain —
 * et le jour où l'ordinateur meurt, on a trois ans de retard. Le rappel
 * ne bloque rien, ne se répète pas dans la journée, et disparaît dès
 * que la copie est faite.
 *
 * Il vit sur le tableau de bord parce que c'est l'écran qu'on ouvre le
 * matin : un avertissement rangé dans les réglages ne serait jamais lu.
 */
export function BackupReminder() {
  const [state, setState] = useState<BackupState | null>(null)

  useEffect(() => {
    apiGet<BackupState>("/api/backups")
      .then(setState)
      .catch(() => setState(null))
  }, [])

  if (!state?.stale) return null

  return (
    <p className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-600">
      <ShieldAlert className="size-4 shrink-0" />
      <span className="min-w-0 flex-1">
        {state.last_copied_at
          ? `Vos sauvegardes n'ont pas quitté cet ordinateur depuis ${state.days_since} jour(s).`
          : "Vos sauvegardes ne sont jamais sorties de cet ordinateur — s'il tombe en panne, tout part avec lui."}{" "}
        Branchez une clé, puis « Copier mes sauvegardes vers… » dans la page
        Académie.
      </span>
    </p>
  )
}
