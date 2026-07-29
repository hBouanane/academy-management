import { useCallback, useEffect, useState } from "react"
import { Trash2 } from "lucide-react"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ApiError, apiGet, apiSend } from "@/lib/api"
import type { PaymentPreview } from "@/lib/api"
import { dhToCentimes, formatDH } from "@/lib/money"

type Props = { enrollmentId: number; studentName: string; onDone: () => void }

const CATEGORY_LABEL: Record<string, string> = {
  discount: "Réduction",
  coupon: "Réduction",
  gift: "Mois offert",
}

export function PayDialog({ enrollmentId, studentName, onDone }: Props) {
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState<PaymentPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [adjustTarget, setAdjustTarget] = useState("")
  const [adjustAmount, setAdjustAmount] = useState("")

  const reload = useCallback(() => {
    apiGet<PaymentPreview>(`/api/enrollments/${enrollmentId}/preview`)
      .then(setPreview)
      .catch((err: Error) => setError(err.message))
  }, [enrollmentId])

  useEffect(() => {
    if (open) reload()
  }, [open, reload])

  const run = (action: () => Promise<unknown>, closeAfter = false) => {
    setError(null)
    setBusy(true)
    action()
      .then(() => {
        if (closeAfter) {
          setOpen(false)
          onDone()
        } else {
          reload()
        }
      })
      .catch((err: Error) => {
        // 409 = the month was already collected (double click, stale dialog).
        if (err instanceof ApiError && err.status === 409) {
          setError("Ce mois est déjà encaissé — la liste va se mettre à jour.")
          setTimeout(() => {
            setOpen(false)
            onDone()
          }, 1200)
        } else {
          setError(err.message)
        }
      })
      .finally(() => setBusy(false))
  }

  const pay = () =>
    run(() => apiSend("POST", "/api/payments", { enrollment_id: enrollmentId }), true)

  const removeAdjustment = (adjustmentId: number) =>
    run(() => apiSend("DELETE", `/api/adjustments/${adjustmentId}`))

  const adjustCentimes = dhToCentimes(adjustAmount)
  const adjustReady =
    adjustTarget !== "" && Number.isFinite(adjustCentimes) && adjustCentimes > 0

  const addManualAdjustment = () => {
    const target = preview?.lines.find(
      (line) => `${line.kind}-${line.ref_id}` === adjustTarget,
    )
    if (!target) return
    run(() =>
      apiSend("POST", `/api/enrollments/${enrollmentId}/adjustments`, {
        kind: "amount",
        value: adjustCentimes,
        reason: `Ajustement manuel — ${target.name}`,
        bearers: [{ kind: target.kind, ref_id: target.ref_id }],
      }),
    )
    setAdjustAmount("")
    setAdjustTarget("")
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setError(null)
          setAdjustAmount("")
          setAdjustTarget("")
        }
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm">Encaisser</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Encaisser — {studentName}</DialogTitle>
        </DialogHeader>

        {preview && (
          <div className="space-y-5">
            <div className="border-border divide-border divide-y rounded-lg border">
              <div className="text-muted-foreground grid grid-cols-4 gap-2 px-3 py-2 text-xs font-medium uppercase">
                <span>Bénéficiaire</span>
                <span className="text-right">Base</span>
                <span className="text-right">Ajust.</span>
                <span className="text-right">Reçoit</span>
              </div>
              {preview.lines.map((line) => (
                <div
                  key={`${line.kind}-${line.ref_id}`}
                  className="grid grid-cols-4 items-center gap-2 px-3 py-2 text-sm"
                >
                  <span className="truncate font-medium">{line.name}</span>
                  <span className="text-muted-foreground text-right">
                    {formatDH(line.base_centimes)}
                  </span>
                  <span
                    className={`text-right ${line.adjustment_centimes < 0 ? "text-destructive" : "text-muted-foreground"}`}
                  >
                    {line.adjustment_centimes
                      ? formatDH(line.adjustment_centimes)
                      : "—"}
                  </span>
                  <span className="text-right font-medium">
                    {formatDH(line.final_centimes)}
                  </span>
                </div>
              ))}
            </div>

            {preview.adjustments.length > 0 && (
              <div className="space-y-2">
                <p className="text-muted-foreground text-xs font-medium uppercase">
                  Réductions appliquées
                </p>
                {preview.adjustments.map((adjustment) => (
                  <div
                    key={adjustment.id}
                    className="border-border flex items-center justify-between rounded-lg border px-3 py-2 text-sm"
                  >
                    <span>
                      {CATEGORY_LABEL[adjustment.category] ?? adjustment.category}
                      {adjustment.reason ? ` · ${adjustment.reason}` : ""}
                      <span className="text-muted-foreground">
                        {" "}
                        (supportée par{" "}
                        {adjustment.bearers.map((b) => b.name).join(", ")})
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="text-destructive">
                        −{formatDH(adjustment.resolved_centimes)}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => removeAdjustment(adjustment.id)}
                        title="Retirer cette réduction"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </span>
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-2">
              <p className="text-muted-foreground text-xs font-medium uppercase">
                Modifier une part manuellement
              </p>
              <div className="flex gap-2">
                <Select value={adjustTarget} onValueChange={setAdjustTarget}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Qui reçoit moins ?" />
                  </SelectTrigger>
                  <SelectContent>
                    {preview.lines.map((line) => (
                      <SelectItem
                        key={`${line.kind}-${line.ref_id}`}
                        value={`${line.kind}-${line.ref_id}`}
                      >
                        {line.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  type="number"
                  min="0"
                  placeholder="Montant DH"
                  value={adjustAmount}
                  onChange={(event) => setAdjustAmount(event.target.value)}
                  className="w-32"
                />
                <Button
                  variant="outline"
                  disabled={!adjustReady || busy}
                  onClick={addManualAdjustment}
                >
                  Réduire
                </Button>
              </div>
              <p className="text-muted-foreground text-xs">
                La réduction est déduite de la part choisie ET du montant payé
                par l'étudiant.
              </p>
            </div>

            {error && <p className="text-destructive text-sm">{error}</p>}

            <DialogFooter className="items-center sm:justify-between">
              <div className="text-sm">
                <span className="text-muted-foreground">Prix {formatDH(preview.price_centimes)} → </span>
                <span className="text-lg font-semibold">
                  {formatDH(preview.net_centimes)}
                </span>
              </div>
              <Button onClick={pay} disabled={busy}>
                {busy ? "…" : `Encaisser ${formatDH(preview.net_centimes)}`}
              </Button>
            </DialogFooter>
          </div>
        )}
        {!preview && !error && (
          <p className="text-muted-foreground text-sm">Chargement…</p>
        )}
        {!preview && error && <p className="text-destructive text-sm">{error}</p>}
      </DialogContent>
    </Dialog>
  )
}
