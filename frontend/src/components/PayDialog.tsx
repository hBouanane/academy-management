import { useCallback, useEffect, useState } from "react"
import { Gift, Pencil, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { ConfirmButton } from "@/components/Confirm"
import { Notice } from "@/components/Notice"
import { useMotifs } from "@/components/MotifInput"
import { ReductionForm } from "@/components/ReductionForm"
import type { ReductionPayload } from "@/components/ReductionForm"
import { ApiError, apiGet, apiSend } from "@/lib/api"
import type { PaymentPreview, PreviewAdjustment, PreviewLine } from "@/lib/api"
import { formatDH } from "@/lib/money"

type Props = {
  enrollmentId: number
  studentName: string
  onDone: () => void
  /** Controlled mode: when provided, no trigger button renders (used to
      chain straight from a fresh enrollment). */
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

const CATEGORY_LABEL: Record<string, string> = {
  discount: "Réduction",
  coupon: "Réduction",
  gift: "Mois offert",
}

export function PayDialog({
  enrollmentId,
  studentName,
  onDone,
  open: controlledOpen,
  onOpenChange,
}: Props) {
  const [internalOpen, setInternalOpen] = useState(false)
  const open = controlledOpen ?? internalOpen
  const setOpen = onOpenChange ?? setInternalOpen
  const [preview, setPreview] = useState<PaymentPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const { motifs, ensure } = useMotifs()

  const reload = useCallback(() => {
    apiGet<PaymentPreview>(`/api/enrollments/${enrollmentId}/preview`)
      .then((data) => {
        setPreview(data)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
  }, [enrollmentId])

  useEffect(() => {
    if (open) reload()
  }, [open, reload])

  const run = (
    action: () => Promise<unknown>,
    { closeAfter = false, isPayment = false } = {},
  ) => {
    setError(null)
    setBusy(true)
    action()
      .then(() => {
        if (closeAfter) {
          setOpen(false)
          onDone()
        } else {
          setEditingId(null)
          setAdding(false)
          reload()
        }
      })
      .catch((err: Error) => {
        // Only a conflicting PAYMENT means "already collected" — any other
        // 409 (locked month, paid guard) shows the API's own explanation.
        if (isPayment && err instanceof ApiError && err.status === 409) {
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
    run(() => apiSend("POST", "/api/payments", { enrollment_id: enrollmentId }), {
      closeAfter: true,
      isPayment: true,
    })

  const submitReduction = async (
    payload: ReductionPayload,
    adjustmentId?: number,
  ) => {
    if (payload.reason) await ensure(payload.reason)
    if (adjustmentId !== undefined) {
      run(() => apiSend("PATCH", `/api/adjustments/${adjustmentId}`, payload))
    } else {
      run(() =>
        apiSend("POST", `/api/enrollments/${enrollmentId}/adjustments`, payload),
      )
    }
  }

  const giftMonth = () =>
    run(() =>
      apiSend("POST", `/api/enrollments/${enrollmentId}/adjustments`, {
        kind: "percent",
        value: 10_000,
        category: "gift",
        reason: "Mois offert",
      }),
    )

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setError(null)
          setEditingId(null)
          setAdding(false)
        }
      }}
    >
      {controlledOpen === undefined && (
        <DialogTrigger asChild>
          <Button size="sm">Encaisser</Button>
        </DialogTrigger>
      )}
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Encaisser — {studentName}</DialogTitle>
        </DialogHeader>

        {preview && (
          <div className="space-y-6">
            <section>
              <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
                Répartition du paiement
              </p>
              <div className="border-border divide-border divide-y overflow-hidden rounded-xl border">
                <div className="text-muted-foreground bg-muted/50 grid grid-cols-[1fr_auto_auto] gap-4 px-4 py-2 text-xs font-medium uppercase">
                  <span>Bénéficiaire</span>
                  <span className="w-24 text-right">Base</span>
                  <span className="w-24 text-right">Reçoit</span>
                </div>
                {preview.lines.map((line) => (
                  <SplitLine key={`${line.kind}-${line.ref_id}`} line={line} />
                ))}
              </div>
            </section>

            <section className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                  Réductions
                </p>
                <div className="flex gap-2">
                  {!adding && editingId === null && (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setAdding(true)}
                      >
                        Ajouter
                      </Button>
                      {preview.adjustments.length === 0 && (
                        <ConfirmButton
                          size="sm"
                          variant="outline"
                          confirmLabel="Offrir ce mois ?"
                          description="Le mois passe à 0 DH pour tout le monde — professeurs, salle et académie ne touchent rien sur un mois offert."
                          onConfirm={giftMonth}
                          disabled={busy}
                        >
                          <Gift className="size-4" /> Mois offert
                        </ConfirmButton>
                      )}
                    </>
                  )}
                </div>
              </div>

              {preview.adjustments.length === 0 && !adding && (
                <p className="text-muted-foreground text-sm">
                  Aucune — le tarif plein s'applique.
                </p>
              )}

              {preview.adjustments.map((adjustment) =>
                editingId === adjustment.id ? (
                  <ReductionForm
                    key={adjustment.id}
                    preview={preview}
                    motifs={motifs}
                    busy={busy}
                    initial={adjustment}
                    onSubmit={(payload) => submitReduction(payload, adjustment.id)}
                    onCancel={() => setEditingId(null)}
                  />
                ) : (
                  <AdjustmentRow
                    key={adjustment.id}
                    adjustment={adjustment}
                    busy={busy}
                    onEdit={() => {
                      setAdding(false)
                      setEditingId(adjustment.id)
                    }}
                    onDelete={() =>
                      run(() =>
                        apiSend("DELETE", `/api/adjustments/${adjustment.id}`),
                      )
                    }
                  />
                ),
              )}

              {adding && (
                <ReductionForm
                  preview={preview}
                  motifs={motifs}
                  busy={busy}
                  onSubmit={(payload) => submitReduction(payload)}
                  onCancel={() => setAdding(false)}
                />
              )}
            </section>

            <Notice message={error} />

            <footer className="border-border flex items-center justify-between border-t pt-4">
              <div>
                {preview.net_centimes !== preview.price_centimes && (
                  <p className="text-muted-foreground text-sm line-through">
                    {formatDH(preview.price_centimes)}
                  </p>
                )}
                <p className="text-2xl font-semibold">
                  {formatDH(preview.net_centimes)}
                </p>
              </div>
              <Button size="lg" onClick={pay} disabled={busy}>
                {busy ? "…" : "Encaisser"}
              </Button>
            </footer>
          </div>
        )}
        {!preview && (
          <p
            className={
              error ? "text-destructive text-sm" : "text-muted-foreground text-sm"
            }
          >
            {error ?? "Chargement…"}
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}

function SplitLine({ line }: { line: PreviewLine }) {
  const reduced = line.adjustment_centimes !== 0
  return (
    <div className="grid grid-cols-[1fr_auto_auto] items-center gap-4 px-4 py-2.5 text-sm">
      <span className="min-w-0 truncate font-medium" title={line.name}>
        {line.name}
        {reduced && (
          <span className="text-destructive ml-2 text-xs">
            {formatDH(line.adjustment_centimes)}
          </span>
        )}
      </span>
      <span
        className={`text-muted-foreground w-24 text-right ${reduced ? "line-through" : ""}`}
      >
        {formatDH(line.base_centimes)}
      </span>
      <span className="w-24 text-right font-semibold">
        {formatDH(line.final_centimes)}
      </span>
    </div>
  )
}

function AdjustmentRow({
  adjustment,
  busy,
  onEdit,
  onDelete,
}: {
  adjustment: PreviewAdjustment
  busy: boolean
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div className="border-border flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-2.5 text-sm">
      <div className="min-w-0">
        <p className="truncate">
          {CATEGORY_LABEL[adjustment.category] ?? adjustment.category}
          {adjustment.reason ? ` · ${adjustment.reason}` : ""}
          {adjustment.kind === "percent" ? ` · ${adjustment.value / 100}%` : ""}
        </p>
        <p className="text-muted-foreground truncate text-xs">
          {adjustment.bearers
            .map(
              (bearer) => `${bearer.name} ${formatDH(bearer.share_centimes)}`,
            )
            .join(" · ")}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <span className="text-destructive font-medium">
          −{formatDH(adjustment.resolved_centimes)}
        </span>
        <Button size="sm" variant="ghost" title="Modifier" onClick={onEdit}>
          <Pencil className="size-4" />
        </Button>
        <ConfirmButton
          size="sm"
          variant="ghost"
          title="Retirer"
          confirmLabel="Retirer cette réduction ?"
          description="Elle sera retirée de cette inscription — le tarif plein revient."
          disabled={busy}
          onConfirm={onDelete}
        >
          <Trash2 className="size-4" />
        </ConfirmButton>
      </div>
    </div>
  )
}
