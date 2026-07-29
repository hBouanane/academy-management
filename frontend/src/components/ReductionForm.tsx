// The sponsors model: one total, then who covers it — each part in DH or %,
// with a live red note while the parts don't sum to the total.

import { useState } from "react"
import { Plus, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { MotifInput } from "@/components/MotifInput"
import type { PaymentPreview, PreviewAdjustment } from "@/lib/api"
import { dhToCentimes, formatDH } from "@/lib/money"

type SponsorRow = { target: string; mode: "amount" | "percent"; value: string }

export type ReductionPayload = {
  kind: "percent" | "amount"
  value: number
  category: string
  reason: string | null
  bearers: {
    kind: string
    ref_id: number
    share_centimes: number | null
    share_bp: number | null
  }[]
}

type Props = {
  preview: PaymentPreview
  motifs: { id: number; label: string }[]
  busy: boolean
  initial?: PreviewAdjustment
  onSubmit: (payload: ReductionPayload) => void
  onCancel?: () => void
}

export function ReductionForm({
  preview,
  motifs,
  busy,
  initial,
  onSubmit,
  onCancel,
}: Props) {
  const [totalMode, setTotalMode] = useState<"amount" | "percent">(
    initial?.kind === "percent" ? "percent" : "amount",
  )
  const [totalValue, setTotalValue] = useState(
    initial ? String(initial.value / 100) : "",
  )
  const [reason, setReason] = useState(initial?.reason ?? "")
  const [sponsors, setSponsors] = useState<SponsorRow[]>(
    initial && initial.bearers.length
      ? initial.bearers.map((bearer) => ({
          target: `${bearer.kind}-${bearer.ref_id}`,
          mode: "amount",
          value: String((bearer.share_centimes ?? 0) / 100),
        }))
      : [{ target: "owner-default", mode: "percent", value: "100" }],
  )

  const ownerLine = preview.lines.find((line) => line.kind === "owner")
  const resolveTarget = (target: string) =>
    target === "owner-default" && ownerLine
      ? ownerLine
      : preview.lines.find((line) => `${line.kind}-${line.ref_id}` === target)

  const numericTotal = Number(totalValue.replace(",", "."))
  const totalCentimes =
    totalMode === "amount"
      ? dhToCentimes(totalValue)
      : Math.round((numericTotal / 100) * preview.price_centimes)

  const sponsorCentimes = sponsors.map((sponsor) => {
    const raw = Number(sponsor.value.replace(",", "."))
    if (!Number.isFinite(raw)) return 0
    return sponsor.mode === "amount"
      ? dhToCentimes(sponsor.value)
      : Math.round((raw / 100) * totalCentimes)
  })
  const sponsorsSum = sponsorCentimes.reduce((sum, value) => sum + value, 0)
  const mismatch = totalCentimes > 0 && sponsorsSum !== totalCentimes
  const targetsValid = sponsors.every((sponsor) => resolveTarget(sponsor.target))
  const valid =
    Number.isFinite(totalCentimes) &&
    totalCentimes > 0 &&
    !mismatch &&
    targetsValid &&
    sponsors.length > 0

  const updateSponsor = (index: number, patch: Partial<SponsorRow>) =>
    setSponsors((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    )

  const submit = () => {
    onSubmit({
      kind: totalMode,
      value:
        totalMode === "amount" ? totalCentimes : Math.round(numericTotal * 100),
      category: initial?.category ?? "discount",
      reason: reason || null,
      bearers: sponsors.map((sponsor, index) => {
        const line = resolveTarget(sponsor.target)!
        return sponsor.mode === "percent"
          ? {
              kind: line.kind,
              ref_id: line.ref_id,
              share_centimes: null,
              share_bp: Math.round(Number(sponsor.value.replace(",", ".")) * 100),
            }
          : {
              kind: line.kind,
              ref_id: line.ref_id,
              share_centimes: sponsorCentimes[index],
              share_bp: null,
            }
      }),
    })
  }

  return (
    <div className="border-border bg-muted/30 space-y-3 rounded-xl border p-4">
      <p className="text-sm font-medium">
        {initial ? "Modifier la réduction" : "Nouvelle réduction"}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground w-16 text-xs">Total</span>
        <Input
          type="number"
          min="0"
          placeholder={totalMode === "amount" ? "100" : "% du prix"}
          value={totalValue}
          onChange={(event) => setTotalValue(event.target.value)}
          className="w-28"
        />
        <Select
          value={totalMode}
          onValueChange={(mode) => setTotalMode(mode as "amount" | "percent")}
        >
          <SelectTrigger className="w-20">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="amount">DH</SelectItem>
            <SelectItem value="percent">%</SelectItem>
          </SelectContent>
        </Select>
        {Number.isFinite(totalCentimes) && totalCentimes > 0 && (
          <span className="text-muted-foreground text-xs">
            = {formatDH(totalCentimes)}
          </span>
        )}
      </div>
      <MotifInput value={reason} onChange={setReason} motifs={motifs} />

      <p className="text-muted-foreground text-xs font-medium uppercase">
        Sponsors — qui couvre cette réduction
      </p>
      {sponsors.map((sponsor, index) => (
        <div key={index} className="flex flex-wrap items-center gap-2">
          <Select
            value={sponsor.target}
            onValueChange={(target) => updateSponsor(index, { target })}
          >
            <SelectTrigger className="min-w-40 flex-1">
              <SelectValue placeholder="Qui ?" />
            </SelectTrigger>
            <SelectContent>
              {preview.lines.map((line) => (
                <SelectItem
                  key={`${line.kind}-${line.ref_id}`}
                  value={
                    sponsor.target === "owner-default" && line.kind === "owner"
                      ? "owner-default"
                      : `${line.kind}-${line.ref_id}`
                  }
                >
                  {line.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="number"
            min="0"
            value={sponsor.value}
            onChange={(event) => updateSponsor(index, { value: event.target.value })}
            className="w-24"
          />
          <Select
            value={sponsor.mode}
            onValueChange={(mode) =>
              updateSponsor(index, { mode: mode as "amount" | "percent" })
            }
          >
            <SelectTrigger className="w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="amount">DH</SelectItem>
              <SelectItem value="percent">%</SelectItem>
            </SelectContent>
          </Select>
          <span className="text-muted-foreground w-20 text-right text-xs">
            {formatDH(sponsorCentimes[index] ?? 0)}
          </span>
          {sponsors.length > 1 && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                setSponsors((current) => current.filter((_, i) => i !== index))
              }
            >
              <X className="size-4" />
            </Button>
          )}
        </div>
      ))}
      <Button
        size="sm"
        variant="ghost"
        onClick={() =>
          setSponsors((current) => [
            ...current,
            { target: "", mode: "amount", value: "" },
          ])
        }
      >
        <Plus className="size-4" /> Ajouter un sponsor
      </Button>

      {mismatch && (
        <p className="text-destructive text-xs font-medium">
          Les parts ({formatDH(sponsorsSum)}) n'égalent pas la réduction (
          {formatDH(totalCentimes)}) —{" "}
          {sponsorsSum < totalCentimes
            ? `il manque ${formatDH(totalCentimes - sponsorsSum)}`
            : `${formatDH(sponsorsSum - totalCentimes)} en trop`}
          .
        </p>
      )}

      <div className="flex gap-2">
        <Button size="sm" onClick={submit} disabled={!valid || busy}>
          {initial ? "Enregistrer" : "Appliquer"}
        </Button>
        {onCancel && (
          <Button size="sm" variant="ghost" onClick={onCancel}>
            Annuler
          </Button>
        )}
      </div>
    </div>
  )
}
