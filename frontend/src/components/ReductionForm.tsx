// The sponsors model: one total, then who covers it — every part in the SAME
// unit (one DH/% switch for the whole list), with live red notes while the
// parts don't sum to the total.

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
import { Notice } from "@/components/Notice"
import type { PaymentPreview, PreviewAdjustment } from "@/lib/api"
import { dhToCentimes, formatDH } from "@/lib/money"

type SponsorRow = { target: string; value: string }
type Unit = "amount" | "percent"

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
  // Subject-scoped rows resolve % against the subject share, not the price —
  // editing them stays in DH to keep the displayed math truthful.
  const subjectScoped = initial?.scope === "subject"
  const [totalMode, setTotalMode] = useState<Unit>(
    initial?.kind === "percent" && !subjectScoped ? "percent" : "amount",
  )
  const [totalValue, setTotalValue] = useState(
    initial
      ? subjectScoped
        ? String(initial.resolved_centimes / 100)
        : String(initial.value / 100)
      : "",
  )
  const [reason, setReason] = useState(initial?.reason ?? "")
  // One unit for every sponsor part — mixing % and DH rows confused everyone.
  const initialPercent =
    !initial ||
    initial.bearers.length === 0 ||
    initial.bearers.every((bearer) => bearer.share_bp !== null)
  const [sponsorMode, setSponsorMode] = useState<Unit>(
    initialPercent ? "percent" : "amount",
  )
  const [sponsors, setSponsors] = useState<SponsorRow[]>(
    initial && initial.bearers.length
      ? initial.bearers.map((bearer) => ({
          target: `${bearer.kind}-${bearer.ref_id}`,
          value: initialPercent
            ? String((bearer.share_bp ?? 0) / 100)
            : String(bearer.share_centimes / 100),
        }))
      : [{ target: "owner-default", value: "100" }],
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
      : Math.floor((numericTotal * 100 * preview.price_centimes) / 10000)

  // Exact mirror of the backend: floor % shares, then give the flooring loss
  // back to the largest % shares — the red note only fires on real mismatch.
  const sponsorCentimes = (() => {
    const raw = sponsors.map((sponsor) => {
      const value = Number(sponsor.value.replace(",", "."))
      if (!Number.isFinite(value)) return 0
      return sponsorMode === "amount"
        ? dhToCentimes(sponsor.value)
        : Math.floor((value * 100 * totalCentimes) / 10000)
    })
    if (sponsorMode === "percent") {
      const order = raw
        .map((value, index) => ({ value, index }))
        .sort((a, b) => b.value - a.value)
        .map(({ index }) => index)
      let difference = totalCentimes - raw.reduce((sum, v) => sum + v, 0)
      if (difference > 0 && order.length && difference <= order.length) {
        for (let offset = 0; difference > 0; offset++, difference--) {
          raw[order[offset % order.length]] += 1
        }
      }
    }
    return raw
  })()
  const sponsorsSum = sponsorCentimes.reduce((sum, value) => sum + value, 0)
  const mismatch = totalCentimes > 0 && sponsorsSum !== totalCentimes

  // Flipping the unit converts the numbers so the parts keep their meaning.
  const switchUnit = (unit: Unit) => {
    if (unit === sponsorMode) return
    setSponsors((current) =>
      current.map((row, index) => {
        const centimes = sponsorCentimes[index] ?? 0
        if (unit === "amount") return { ...row, value: String(centimes / 100) }
        if (totalCentimes <= 0) return row
        return {
          ...row,
          value: String(Math.round((centimes * 10000) / totalCentimes) / 100),
        }
      }),
    )
    setSponsorMode(unit)
  }

  // The zero-floor rule: a share can be reduced to zero, never below.
  // When editing, this adjustment's own current cut comes back first.
  const capFor = (target: string) => {
    const line = resolveTarget(target)
    if (!line) return 0
    const previousCut =
      initial?.bearers.find(
        (bearer) => bearer.kind === line.kind && bearer.ref_id === line.ref_id,
      )?.share_centimes ?? 0
    return line.final_centimes + previousCut
  }
  const overCapIndex = sponsors.findIndex(
    (sponsor, index) =>
      resolveTarget(sponsor.target) !== undefined &&
      sponsorCentimes[index] > capFor(sponsor.target),
  )
  const targetsValid = sponsors.every((sponsor) => resolveTarget(sponsor.target))
  // Client rule: an over-cap part WARNS (red note) but never blocks.
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
        return sponsorMode === "percent"
          ? {
              kind: line.kind,
              ref_id: line.ref_id,
              share_centimes: null,
              share_bp: Math.round(
                Number(sponsor.value.replace(",", ".")) * 100,
              ),
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
          onValueChange={(mode) => setTotalMode(mode as Unit)}
          disabled={subjectScoped}
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

      <div className="flex items-center justify-between gap-2">
        <p className="text-muted-foreground text-xs font-medium uppercase">
          Sponsors — qui couvre cette réduction
        </p>
        <Select
          value={sponsorMode}
          onValueChange={(unit) => switchUnit(unit as Unit)}
        >
          <SelectTrigger size="sm" className="w-18">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="amount">DH</SelectItem>
            <SelectItem value="percent">%</SelectItem>
          </SelectContent>
        </Select>
      </div>
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
            onChange={(event) =>
              updateSponsor(index, { value: event.target.value })
            }
            className="w-24"
          />
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
          setSponsors((current) => [...current, { target: "", value: "" }])
        }
      >
        <Plus className="size-4" /> Ajouter un sponsor
      </Button>

      <Notice
        message={
          mismatch
            ? `Les parts (${formatDH(sponsorsSum)}) n'égalent pas la réduction (${formatDH(
                totalCentimes,
              )}) — ${
                sponsorsSum < totalCentimes
                  ? `il manque ${formatDH(totalCentimes - sponsorsSum)}`
                  : `${formatDH(sponsorsSum - totalCentimes)} en trop`
              }.`
            : null
        }
      />
      <Notice
        message={
          overCapIndex !== -1
            ? `Attention : ${
                resolveTarget(sponsors[overCapIndex].target)?.name
              } ne reçoit que ${formatDH(
                capFor(sponsors[overCapIndex].target),
              )} — sa part deviendra négative. Autorisé, mais vérifiez.`
            : null
        }
      />

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
