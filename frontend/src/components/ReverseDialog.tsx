import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Notice } from "@/components/Notice"
import { apiSend } from "@/lib/api"

type Props = { paymentId: number; onDone: () => void }

export function ReverseDialog({ paymentId, onDone }: Props) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setReason("")
    setError(null)
    setBusy(false)
  }

  const submit = () => {
    setError(null)
    setBusy(true)
    apiSend("POST", `/api/payments/${paymentId}/reverse`, {
      reason: reason || null,
    })
      .then(() => {
        setOpen(false)
        reset()
        onDone()
      })
      .catch((err: Error) => {
        setError(err.message)
        setBusy(false)
      })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) reset()
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          Annuler paiement
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Annuler ce paiement ?</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          Le paiement sera contre-passé dans le registre (rien n'est effacé) et
          le mois redeviendra impayé.
        </p>
        <div className="space-y-2">
          <Label>Motif</Label>
          <Input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Chèque refusé…"
          />
        </div>
        <Notice message={error} />
        <DialogFooter>
          <Button variant="destructive" onClick={submit} disabled={busy}>
            {busy ? "…" : "Contre-passer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
