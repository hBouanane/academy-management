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
import { monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { useMotifs } from "@/components/MotifInput"
import { ReductionForm } from "@/components/ReductionForm"
import type { ReductionPayload } from "@/components/ReductionForm"
import { useToast } from "@/components/Toast"
import { Input } from "@/components/ui/input"
import { ApiError, apiGet, apiSend } from "@/lib/api"
import type { PaymentPreview, PreviewAdjustment, PreviewLine } from "@/lib/api"
import { dhToCentimes, formatDH } from "@/lib/money"
import { useAlert } from "@/lib/alert"

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
  const [error, setError] = useAlert()
  const fail = (message: string) => setError(message)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const [giftOpen, setGiftOpen] = useState(false)
  const { motifs, ensure } = useMotifs()
  const toast = useToast()

  // The amount actually handed over — less than the net posts an avance.
  const [amount, setAmount] = useState("")

  const reload = useCallback(() => {
    apiGet<PaymentPreview>(`/api/enrollments/${enrollmentId}/preview`)
      .then((data) => {
        setPreview(data)
        setAmount(String(data.net_centimes / 100))
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
  }, [enrollmentId, setError])

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

  // Mois offert : le net est à zéro, il n'y a rien à saisir ni à encaisser.
  const nothingToPay = preview !== null && preview.net_centimes === 0

  const pay = () => {
    const centimes = nothingToPay ? 0 : dhToCentimes(amount)
    if (!Number.isFinite(centimes) || centimes < 0) {
      fail("Entrez un montant valide.")
      return
    }
    if (preview !== null && centimes > preview.net_centimes) {
      fail(
        `L'étudiant ne peut pas payer plus que le prix — ${formatDH(
          preview.net_centimes,
        )} au maximum.`,
      )
      return
    }
    if (centimes === 0 && !nothingToPay) {
      fail(
        "0 DH n'encaisse rien — saisissez ce que l'étudiant remet, ou" +
          " utilisez « Mois offert » si c'est gratuit.",
      )
      return
    }
    const partial =
      preview !== null && centimes < preview.net_centimes
        ? { amount_centimes: centimes }
        : {}
    run(
      () =>
        apiSend("POST", "/api/payments", {
          enrollment_id: enrollmentId,
          ...partial,
        }).then((posted) => {
          // La fenêtre se referme : sans un mot, on doute d'avoir cliqué.
          toast(
            nothingToPay
              ? `Mois offert validé — ${studentName}`
              : `Encaissé ${formatDH(centimes)} — ${studentName}`,
          )
          return posted
        }),
      { closeAfter: true, isPayment: true },
    )
  }

  const partialCentimes = preview ? dhToCentimes(amount) : 0
  const isAvance =
    preview !== null &&
    Number.isFinite(partialCentimes) &&
    partialCentimes > 0 &&
    partialCentimes < preview.net_centimes

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

  const giftMonth = (recurring: boolean) => {
    setGiftOpen(false)
    run(() =>
      apiSend("POST", `/api/enrollments/${enrollmentId}/adjustments`, {
        kind: "percent",
        value: 10_000,
        category: "gift",
        reason: "Mois offert",
        recurring,
      }),
    )
  }

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
          <DialogTitle>
            Encaisser — {studentName}
            {preview && (
              <span className="text-muted-foreground capitalize">
                {" "}
                · {monthLabel(preview.month)}
              </span>
            )}
          </DialogTitle>
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
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy}
                          onClick={() => setGiftOpen(true)}
                        >
                          <Gift className="size-4" /> Mois offert
                        </Button>
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

            <Notice alert={error} />

            <footer className="border-border space-y-3 border-t pt-4">
              <div className="flex items-center justify-between">
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
                <div className="flex items-center gap-2">
                  {!nothingToPay && (
                    <div className="text-right">
                      <p className="text-muted-foreground text-xs">
                        Montant reçu (DH)
                      </p>
                      <Input
                        value={amount}
                        onChange={(event) => setAmount(event.target.value)}
                        inputMode="decimal"
                        className="h-9 w-28 text-right"
                      />
                    </div>
                  )}
                  <Button size="lg" onClick={pay} disabled={busy}>
                    {busy
                      ? "…"
                      : nothingToPay
                        ? "Valider le mois offert"
                        : isAvance
                          ? "Encaisser l'avance"
                          : "Encaisser"}
                  </Button>
                </div>
              </div>
              {nothingToPay && (
                <p className="text-muted-foreground text-xs">
                  Rien à encaisser : le mois est offert. Validez simplement —
                  personne ne touche quoi que ce soit, et l'étudiant ne doit
                  plus rien.
                </p>
              )}
              {isAvance && (
                <p className="text-muted-foreground text-xs">
                  Avance : chacun (professeurs, salle) reçoit sa part{" "}
                  <span className="font-medium">entière</span> — l'académie avance
                  les{" "}
                  <span className="font-medium">
                    {formatDH(preview.net_centimes - partialCentimes)}
                  </span>{" "}
                  manquants jusqu'à ce que l'étudiant complète.
                </p>
              )}
            </footer>
          </div>
        )}
        {!preview && (
          <p
            className={
              error.message ? "text-destructive text-sm" : "text-muted-foreground text-sm"
            }
          >
            {error.message ?? "Chargement…"}
          </p>
        )}
      </DialogContent>

      {giftOpen && (
        <Dialog open onOpenChange={(next) => !next && setGiftOpen(false)}>
          <DialogContent className="sm:max-w-sm" showCloseButton={false}>
            <DialogHeader>
              <DialogTitle>Offrir ce mois ?</DialogTitle>
            </DialogHeader>
            <p className="text-muted-foreground text-sm">
              Le mois passe à 0 DH pour tout le monde — professeurs, salle et
              académie ne touchent rien. Offrir une seule fois, ou chaque mois ?
            </p>
            <div className="flex flex-wrap justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setGiftOpen(false)}>
                Annuler
              </Button>
              <Button size="sm" variant="outline" onClick={() => giftMonth(false)}>
                Ce mois uniquement
              </Button>
              <Button size="sm" onClick={() => giftMonth(true)}>
                Chaque mois
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
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
          {adjustment.recurring ? (
            <span className="text-muted-foreground text-xs"> · chaque mois</span>
          ) : null}
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
