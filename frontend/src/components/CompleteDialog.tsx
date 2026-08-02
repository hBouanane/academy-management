// Completing an avance: the student brings the rest (or part of it) — the
// cash goes straight back to the académie, which fronted everyone's shares.

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
import { apiSend } from "@/lib/api"
import { dhToCentimes, formatDH } from "@/lib/money"

type Props = {
  paymentId: number
  studentName: string
  remainingCentimes: number
  onClose: () => void
  onDone: () => void
}

export function CompleteDialog({
  paymentId,
  studentName,
  remainingCentimes,
  onClose,
  onDone,
}: Props) {
  const [amount, setAmount] = useState(String(remainingCentimes / 100))
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = () => {
    const centimes = dhToCentimes(amount)
    if (!Number.isFinite(centimes) || centimes <= 0) {
      setNote("Entrez un montant valide.")
      return
    }
    setNote(null)
    setBusy(true)
    apiSend("POST", `/api/payments/${paymentId}/complete`, {
      amount_centimes: centimes,
    })
      .then(onDone)
      .catch((err: Error) => {
        setNote(err.message)
        setBusy(false)
      })
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Compléter l'avance — {studentName}</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          Il reste <span className="font-medium">{formatDH(remainingCentimes)}</span>{" "}
          à encaisser. Ce versement revient à l'académie, qui a avancé les parts
          de tout le monde.
        </p>
        <div className="space-y-2">
          <Label>Montant reçu (DH)</Label>
          <Input
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            inputMode="decimal"
          />
        </div>
        <Notice message={note} />
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : "Encaisser"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
