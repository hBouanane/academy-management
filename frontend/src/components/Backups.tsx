import { useCallback, useEffect, useState } from "react"
import { HardDriveDownload, ShieldAlert } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"
import type { BackupState } from "@/lib/api"

/**
 * Carrying the backups away.
 *
 * A copy of the academy is taken at every close, by itself, on this
 * computer. It saves you from a slip of the hand -- not from a laptop
 * stolen, drowned or dead.
 *
 * Requiring a stick to stay plugged in would not work: nobody leaves one
 * there, and an automatic copy that fails silently is the worst kind of
 * safety net, the kind you believe in. Hence a deliberate act: he plugs
 * it in when he thinks of it, he clicks, everything goes. The app
 * remembers where, and reminds him when it has been too long.
 */
export function Backups({ onError }: { onError: (message: string) => void }) {
  const [state, setState] = useState<BackupState | null>(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  const load = useCallback(
    () =>
      apiGet<BackupState>("/api/backups")
        .then(setState)
        .catch(() => setState(null)),
    [],
  )
  useEffect(() => {
    void load()
  }, [load])

  const copy = () => {
    setBusy(true)
    apiSend<{ copied: number; cancelled?: boolean; destination?: string }>(
      "POST",
      "/api/backups/copy",
      {},
    )
      .then((done) => {
        if (done.cancelled) return
        toast(
          done.copied === 0
            ? "Tout y était déjà — vos sauvegardes sont à jour sur ce support"
            : `${done.copied} sauvegarde(s) copiée(s) vers ${done.destination}`,
        )
        void load()
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => setBusy(false))
  }

  return (
    <div className="surface-card space-y-3 p-6">
      <div>
        <Label>Sauvegardes</Label>
        <p className="text-muted-foreground text-xs">
          Une copie complète de l'académie est prise à chaque fermeture, sur
          cet ordinateur. Elle vous sauve d'une fausse manœuvre — pas d'un
          ordinateur perdu. Pour ça, emportez-les sur une clé.
        </p>
      </div>

      <p className="text-muted-foreground text-sm">
        {state === null || state.count === 0
          ? "Aucune copie pour l'instant — la première sera prise à la fermeture."
          : `${state.count} copie(s) sur cet ordinateur, dont ${state.uncopied} jamais emportée(s).`}
        {state?.last_copied_at && (
          <>
            {" "}
            Dernier départ vers un support externe il y a{" "}
            {state.days_since === 0 ? "moins d'un jour" : `${state.days_since} jour(s)`}.
          </>
        )}
      </p>

      {state?.stale && (
        <p className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-sm text-amber-600">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" />
          {`${state.uncopied} sauvegarde(s) n'ont jamais quitté cet ordinateur.`}{" "}
          Branchez votre clé et copiez-les.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button disabled={busy} onClick={copy}>
          <HardDriveDownload className="size-4" />
          Copier mes sauvegardes vers…
        </Button>
        {state?.destination && (
          <span className="text-muted-foreground font-mono text-xs break-all">
            {state.destination}
          </span>
        )}
      </div>
    </div>
  )
}
