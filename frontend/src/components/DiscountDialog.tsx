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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { MotifInput, useMotifs } from "@/components/MotifInput"
import { apiSend } from "@/lib/api"
import { dhToCentimes } from "@/lib/money"

type Props = { enrollmentId: number; onDone: () => void }

export function DiscountDialog({ enrollmentId, onDone }: Props) {
  const [open, setOpen] = useState(false)
  const [amount, setAmount] = useState("")
  const [category, setCategory] = useState("discount")
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { motifs, ensure } = useMotifs()

  const reset = () => {
    setAmount("")
    setReason("")
    setError(null)
    setBusy(false)
  }

  const isGift = category === "gift"
  const centimes = dhToCentimes(amount)
  const valid = isGift || (Number.isFinite(centimes) && centimes > 0)

  const submit = async () => {
    setError(null)
    setBusy(true)
    await ensure(reason)
    apiSend("POST", `/api/enrollments/${enrollmentId}/adjustments`, {
      // A gift month is simply a 100% reduction of the package.
      kind: isGift ? "percent" : "amount",
      value: isGift ? 10_000 : centimes,
      category,
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
          Réduction
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Réduction — supportée par le propriétaire</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Type</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="discount">Réduction (montant)</SelectItem>
                <SelectItem value="gift">Mois offert (100%)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {!isGift && (
            <div className="space-y-2">
              <Label>Montant (DH)</Label>
              <Input
                type="number"
                min="0"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                placeholder="50"
              />
            </div>
          )}
          <div className="space-y-2">
            <Label>Motif</Label>
            <MotifInput value={reason} onChange={setReason} motifs={motifs} />
          </div>
          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={!valid || busy}>
            {busy ? "…" : "Appliquer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
