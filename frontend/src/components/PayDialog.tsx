import { useCallback, useEffect, useState } from "react"
import { Pencil, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
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
import { ConfirmButton } from "@/components/Confirm"
import { MotifInput, useMotifs } from "@/components/MotifInput"
import { ApiError, apiGet, apiSend } from "@/lib/api"
import type { PaymentPreview, PreviewAdjustment, PreviewLine } from "@/lib/api"
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
  const [editingId, setEditingId] = useState<number | null>(null)
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

  const run = (action: () => Promise<unknown>, closeAfter = false) => {
    setError(null)
    setBusy(true)
    action()
      .then(() => {
        if (closeAfter) {
          setOpen(false)
          onDone()
        } else {
          setEditingId(null)
          reload()
        }
      })
      .catch((err: Error) => {
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

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setError(null)
          setEditingId(null)
        }
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm">Encaisser</Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90svh] max-w-xl overflow-y-auto">
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
              <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                Réductions
              </p>
              {preview.adjustments.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  Aucune — le tarif plein s'applique.
                </p>
              )}
              {preview.adjustments.map((adjustment) =>
                editingId === adjustment.id ? (
                  <AdjustmentEditor
                    key={adjustment.id}
                    adjustment={adjustment}
                    preview={preview}
                    motifs={motifs}
                    ensureMotif={ensure}
                    busy={busy}
                    onCancel={() => setEditingId(null)}
                    onSave={(body) =>
                      run(() =>
                        apiSend("PATCH", `/api/adjustments/${adjustment.id}`, body),
                      )
                    }
                  />
                ) : (
                  <AdjustmentRow
                    key={adjustment.id}
                    adjustment={adjustment}
                    busy={busy}
                    onEdit={() => setEditingId(adjustment.id)}
                    onDelete={() =>
                      run(() =>
                        apiSend("DELETE", `/api/adjustments/${adjustment.id}`),
                      )
                    }
                  />
                ),
              )}
              {editingId === null && (
                <ManualReduction
                  preview={preview}
                  motifs={motifs}
                  ensureMotif={ensure}
                  busy={busy}
                  onApply={(body) =>
                    run(() =>
                      apiSend(
                        "POST",
                        `/api/enrollments/${enrollmentId}/adjustments`,
                        body,
                      ),
                    )
                  }
                />
              )}
            </section>

            {error && <p className="text-destructive text-sm">{error}</p>}

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
    <div className="border-border flex items-center justify-between gap-3 rounded-xl border px-4 py-2.5 text-sm">
      <div className="min-w-0">
        <p className="truncate">
          {CATEGORY_LABEL[adjustment.category] ?? adjustment.category}
          {adjustment.reason ? ` · ${adjustment.reason}` : ""}
        </p>
        <p className="text-muted-foreground truncate text-xs">
          supportée par{" "}
          {adjustment.bearers.map((bearer) => bearer.name).join(", ")}
          {adjustment.kind === "percent" ? ` · ${adjustment.value / 100}%` : ""}
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
          disabled={busy}
          onConfirm={onDelete}
        >
          <Trash2 className="size-4" />
        </ConfirmButton>
      </div>
    </div>
  )
}

type ReductionBody = {
  kind: "percent" | "amount"
  value: number
  reason: string | null
  bearers?: { kind: string; ref_id: number }[]
}

function ManualReduction({
  preview,
  motifs,
  ensureMotif,
  busy,
  onApply,
}: {
  preview: PaymentPreview
  motifs: { id: number; label: string }[]
  ensureMotif: (label: string) => Promise<void>
  busy: boolean
  onApply: (body: ReductionBody) => void
}) {
  const [target, setTarget] = useState("")
  const [mode, setMode] = useState<"amount" | "percent">("amount")
  const [value, setValue] = useState("")
  const [reason, setReason] = useState("")

  const line = preview.lines.find(
    (candidate) => `${candidate.kind}-${candidate.ref_id}` === target,
  )
  const numeric = Number(value.replace(",", "."))
  const centimes =
    mode === "amount"
      ? dhToCentimes(value)
      : Math.round((numeric / 100) * preview.price_centimes)
  // A share can go down to zero, never below — the cap the owner asked for.
  const cap = line ? line.final_centimes : 0
  const valid =
    line !== undefined &&
    value !== "" &&
    Number.isFinite(centimes) &&
    centimes > 0 &&
    centimes <= cap

  const apply = async () => {
    if (!line) return
    await ensureMotif(reason)
    onApply({
      kind: "amount",
      value: centimes,
      reason: reason || null,
      bearers: [{ kind: line.kind, ref_id: line.ref_id }],
    })
    setValue("")
    setReason("")
    setTarget("")
  }

  return (
    <div className="border-border bg-muted/30 space-y-3 rounded-xl border border-dashed p-4">
      <p className="text-sm font-medium">Réduire une part</p>
      <div className="flex flex-wrap gap-2">
        <Select value={target} onValueChange={setTarget}>
          <SelectTrigger className="min-w-44 flex-1">
            <SelectValue placeholder="Qui reçoit moins ?" />
          </SelectTrigger>
          <SelectContent>
            {preview.lines.map((candidate) => (
              <SelectItem
                key={`${candidate.kind}-${candidate.ref_id}`}
                value={`${candidate.kind}-${candidate.ref_id}`}
              >
                {candidate.name} — {formatDH(candidate.final_centimes)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={mode}
          onValueChange={(next) => setMode(next as "amount" | "percent")}
        >
          <SelectTrigger className="w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="amount">DH</SelectItem>
            <SelectItem value="percent">%</SelectItem>
          </SelectContent>
        </Select>
        <Input
          type="number"
          min="0"
          placeholder={mode === "amount" ? "Montant" : "% du forfait"}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className="w-32"
        />
      </div>
      <MotifInput value={reason} onChange={setReason} motifs={motifs} />
      {line && value !== "" && !valid && (
        <p className="text-destructive text-xs">
          Maximum pour {line.name} : {formatDH(cap)}.
        </p>
      )}
      <Button size="sm" variant="outline" disabled={!valid || busy} onClick={apply}>
        Appliquer la réduction
      </Button>
    </div>
  )
}

function AdjustmentEditor({
  adjustment,
  preview,
  motifs,
  ensureMotif,
  busy,
  onCancel,
  onSave,
}: {
  adjustment: PreviewAdjustment
  preview: PaymentPreview
  motifs: { id: number; label: string }[]
  ensureMotif: (label: string) => Promise<void>
  busy: boolean
  onCancel: () => void
  onSave: (body: ReductionBody) => void
}) {
  const [mode, setMode] = useState<"amount" | "percent">(
    adjustment.kind === "percent" ? "percent" : "amount",
  )
  const [value, setValue] = useState(String(adjustment.value / 100))
  const [reason, setReason] = useState(adjustment.reason ?? "")
  const [bearer, setBearer] = useState(
    adjustment.bearers[0]
      ? `${adjustment.bearers[0].kind}-${adjustment.bearers[0].ref_id}`
      : "",
  )

  const bearerLine = preview.lines.find(
    (line) => `${line.kind}-${line.ref_id}` === bearer,
  )
  const numeric = Number(value.replace(",", "."))
  const resolved =
    mode === "amount"
      ? Math.round(numeric * 100)
      : Math.round((numeric / 100) * preview.price_centimes)
  const valid = value !== "" && Number.isFinite(resolved) && resolved > 0

  const save = async () => {
    await ensureMotif(reason)
    onSave({
      kind: mode,
      value: mode === "amount" ? resolved : Math.round(numeric * 100),
      reason: reason || null,
      bearers: bearerLine
        ? [{ kind: bearerLine.kind, ref_id: bearerLine.ref_id }]
        : undefined,
    })
  }

  return (
    <div className="border-border bg-muted/30 space-y-3 rounded-xl border p-4">
      <p className="text-sm font-medium">Modifier la réduction</p>
      <div className="flex flex-wrap gap-2">
        <Select value={bearer} onValueChange={setBearer}>
          <SelectTrigger className="min-w-44 flex-1">
            <SelectValue placeholder="Supportée par…" />
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
        <Select
          value={mode}
          onValueChange={(next) => setMode(next as "amount" | "percent")}
        >
          <SelectTrigger className="w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="amount">DH</SelectItem>
            <SelectItem value="percent">%</SelectItem>
          </SelectContent>
        </Select>
        <Input
          type="number"
          min="0"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className="w-32"
        />
      </div>
      <MotifInput value={reason} onChange={setReason} motifs={motifs} />
      <p className="text-muted-foreground text-xs">
        Aperçu : −{formatDH(Number.isFinite(resolved) ? Math.max(resolved, 0) : 0)}
      </p>
      <div className="flex gap-2">
        <Button size="sm" onClick={save} disabled={!valid || busy}>
          Enregistrer
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Annuler
        </Button>
      </div>
    </div>
  )
}
