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
import { apiSend } from "@/lib/api"
import { dhToCentimes } from "@/lib/money"

type Props = { enrollmentId: number; onDone: () => void }

export function DiscountDialog({ enrollmentId, onDone }: Props) {
  const [open, setOpen] = useState(false)
  const [amount, setAmount] = useState("")
  const [category, setCategory] = useState("discount")
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)

  const submit = () => {
    setError(null)
    apiSend("POST", `/api/enrollments/${enrollmentId}/adjustments`, {
      kind: "amount",
      value: dhToCentimes(amount),
      category,
      reason: reason || null,
    })
      .then(() => {
        setOpen(false)
        setAmount("")
        setReason("")
        onDone()
      })
      .catch((err: Error) => setError(err.message))
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
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
            <Label>Montant (DH)</Label>
            <Input
              type="number"
              min="0"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="50"
            />
          </div>
          <div className="space-y-2">
            <Label>Type</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="discount">Réduction</SelectItem>
                <SelectItem value="coupon">Coupon</SelectItem>
                <SelectItem value="gift">Cadeau</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Motif</Label>
            <Input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Situation familiale…"
            />
          </div>
          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={!amount}>
            Appliquer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
