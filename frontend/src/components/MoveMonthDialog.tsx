// Déplacer une inscription vers le bon mois.
//
// Le cas : l'élève s'inscrit et paie septembre, la saisie part sur
// octobre. Rien ici n'est annulé -- il s'est inscrit, il a payé, les deux
// sont vrais. L'écriture est simplement dans le mauvais tiroir.
//
// Un geste et non quatre. Contre-passer, supprimer, réinscrire, repayer à
// la main, ce sont quatre occasions de se tromper encore -- alors que la
// raison d'être ici est justement une faute de frappe.

import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Notice } from "@/components/Notice"
import { monthLabel } from "@/components/MonthNav"
import { apiSend } from "@/lib/api"
import { currentMonth } from "@/lib/money"
import { useAlert } from "@/lib/alert"

export function MoveMonthDialog({
  enrollmentId,
  studentName,
  month,
  onClose,
  onDone,
}: {
  enrollmentId: number
  studentName: string
  /** Le mois où l'inscription se trouve aujourd'hui. */
  month: string
  onClose: () => void
  onDone: () => void
}) {
  const [target, setTarget] = useState(month)
  const [note, setNote] = useAlert()
  const [busy, setBusy] = useState(false)

  const submit = () => {
    setNote(null)
    setBusy(true)
    apiSend("POST", `/api/enrollments/${enrollmentId}/move`, { month: target })
      .then(onDone)
      .catch((err: Error) => {
        setNote(err.message)
        setBusy(false)
      })
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Déplacer vers un autre mois — {studentName}</DialogTitle>
        </DialogHeader>

        <p className="text-muted-foreground text-sm">
          Rien n'est annulé : le forfait, les matières, les réductions et le
          paiement suivent tels quels. Seul le mois change.
        </p>

        <div className="space-y-1.5">
          <Label htmlFor="move-month">De {monthLabel(month)} vers</Label>
          <Input
            id="move-month"
            type="month"
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            className="w-44"
          />
        </div>

        {/* Un mois clos accepte la correction : on s'aperçoit d'une
            mauvaise saisie après coup, et refuser rendrait la correction
            impossible au moment précis où elle sert. Mais ses chiffres
            bougent, et cela se dit avant le clic, pas après. */}
        {target < currentMonth() && target !== month && (
          <p className="text-xs text-amber-600">
            {monthLabel(target)} est un mois clos. Ses chiffres changeront, et
            ce qui reste à verser aux professeurs de ce mois avec. Le
            déplacement est inscrit au journal.
          </p>
        )}

        {/* Dit à l'avance ce qui sera refusé, plutôt que de le découvrir
            après avoir cliqué. */}
        <p className="text-muted-foreground text-xs">
          Impossible si l'élève a déjà une inscription sur le mois visé, ou si
          le professeur y a été soldé.
        </p>

        <Notice alert={note} />
        <DialogFooter>
          <Button onClick={submit} disabled={busy || target === month}>
            {busy ? "…" : `Déplacer vers ${monthLabel(target)}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
