import { useEffect, useState } from "react"
import { ShieldAlert } from "lucide-react"

import { apiGet } from "@/lib/api"
import type { BackupState } from "@/lib/api"

/**
 * The reminder that beats relying on discipline.
 *
 * Carrying your backups away is the kind of task always put off until
 * tomorrow -- and the day the computer dies, you are three years behind.
 *
 * But a permanent warning becomes part of the furniture: this one stays
 * quiet until there is genuinely something to lose -- thirty working
 * days that never left this machine. And since a snapshot is only taken
 * when the database moved, thirty means thirty real days, not thirty
 * openings to check a figure.
 *
 * It lives on the dashboard because that is the screen opened in the
 * morning: a warning filed away in the settings would never be read.
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
        {state.uncopied} sauvegarde(s) n'ont jamais quitté cet ordinateur —
        s'il tombe en panne, elles partent avec lui. Branchez une clé, puis
        « Copier mes sauvegardes vers… » dans la page Académie.
      </span>
    </p>
  )
}
