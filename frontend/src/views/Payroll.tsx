// La paie du mois : ce que chaque professeur a gagné, ce qui lui a déjà été
// remis, ce qu'il reste à verser — et ce que les impayés coûtent vraiment.
//
// La règle du client, en chiffres : la salle et l'académie ne touchent que
// sur les élèves qui paient, donc leur part d'un impayé n'est simplement
// jamais encaissée ; la part professeur, elle, est à la charge de
// l'académie — le professeur est payé quoi qu'il arrive.

import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ConfirmButton } from "@/components/Confirm"
import { MonthNav, monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import type { Academy, OverviewRow, PayoutRow } from "@/lib/api"
import { useCountUp } from "@/lib/anim"
import { dhToCentimes, formatDH } from "@/lib/money"

type Props = { month: string; setMonth: (month: string) => void }

export function Payroll({ month, setMonth }: Props) {
  const [rows, setRows] = useState<PayoutRow[]>([])
  const [overview, setOverview] = useState<OverviewRow[]>([])
  const [academy, setAcademy] = useState<Academy | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    apiGet<PayoutRow[]>(`/api/payouts?month=${month}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message))
    apiGet<OverviewRow[]>(`/api/months/${month}/overview`)
      .then(setOverview)
      .catch(() => setOverview([]))
    apiGet<Academy[]>("/api/academies")
      .then(([first]) => setAcademy(first ?? null))
      .catch(() => {})
  }, [month])
  useEffect(reload, [reload])

  const payTeacher = (teacherId: number, amount?: number) =>
    apiSend("POST", `/api/teachers/${teacherId}/payouts`, {
      month,
      ...(amount === undefined ? {} : { amount_centimes: amount }),
    })
      .then(reload)
      .catch((err: Error) => setError(err.message))

  const cancelPayout = (payoutId: number) =>
    apiSend("DELETE", `/api/payouts/${payoutId}`)
      .then(reload)
      .catch((err: Error) => setError(err.message))

  const earned = rows.reduce((sum, row) => sum + row.earned_centimes, 0)
  const paid = rows.reduce((sum, row) => sum + row.paid_centimes, 0)
  const remaining = rows.reduce((sum, row) => sum + row.remaining_centimes, 0)

  // Ce que les impayés du mois représentent, calculé sur la répartition
  // réelle de chaque inscription (réductions comprises), pas sur un
  // pourcentage plaqué.
  const unpaid = overview.filter(
    (row) => row.enrollment !== null && !row.enrollment.paid,
  )
  const unpaidTotal = unpaid.reduce(
    (sum, row) => sum + (row.enrollment?.net_centimes ?? 0),
    0,
  )
  const partOf = (kinds: string[]) =>
    unpaid.reduce(
      (sum, row) =>
        sum +
        (row.enrollment?.split ?? [])
          .filter((chip) => kinds.includes(chip.kind))
          .reduce((inner, chip) => inner + chip.final_centimes, 0),
      0,
    )
  const houseLost = partOf(["venue", "owner"])
  const teacherCharge = partOf(["teacher"])
  const guaranteed = unpaid.reduce(
    (sum, row) => sum + (row.enrollment?.guaranteed_centimes ?? 0),
    0,
  )
  const housePct = academy
    ? (academy.venue_bp + academy.owner_bp) / 100
    : null
  const teacherPct = housePct === null ? null : 100 - housePct

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-medium tracking-tight">Paie</h2>
          <p className="text-muted-foreground text-sm">
            Fin de mois : ce que vous devez à chaque professeur, et ce que les
            impayés coûtent réellement
          </p>
        </div>
        <MonthNav month={month} setMonth={setMonth} />
      </header>

      <Notice message={error} />

      <section className="grid gap-4 lg:grid-cols-3">
        <StatCard label={`Gagné par les professeurs — ${monthLabel(month)}`} value={earned} />
        <StatCard label="Déjà versé" value={paid} tone="success" />
        <StatCard label="Reste à verser" value={remaining} tone="alert" />
      </section>

      <div className="surface-card p-5">
        <h3 className="font-medium">Ce que les impayés coûtent</h3>
        <p className="text-muted-foreground mb-4 text-sm">
          La salle et l'académie ne touchent que sur les élèves qui paient. La
          part des professeurs, elle, est à la charge de l'académie.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile
            label={`Total impayé — ${monthLabel(month)}`}
            value={unpaidTotal}
            hint={`${unpaid.length} élève(s)`}
          />
          <Tile
            label={
              housePct === null
                ? "Part salle + académie"
                : `Part salle + académie (${housePct}%)`
            }
            value={houseLost}
            hint="jamais encaissée"
            tone="muted"
          />
          <Tile
            label={
              teacherPct === null
                ? "Part professeurs"
                : `Part professeurs (${teacherPct}%)`
            }
            value={teacherCharge}
            hint={
              guaranteed > 0
                ? `à la charge de l'académie · ${formatDH(guaranteed)} déjà soldé`
                : "à la charge de l'académie"
            }
            tone="alert"
          />
        </div>
      </div>

      <div className="surface-card p-5">
        <h3 className="mb-3 font-medium">Versements aux professeurs</h3>
        <div className="table-wrap">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Professeur</TableHead>
                <TableHead className="text-right">Gagné</TableHead>
                <TableHead className="text-right">Versé</TableHead>
                <TableHead className="text-right">Reste</TableHead>
                <TableHead>Versements</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows
                .filter((row) => row.earned_centimes > 0 || row.paid_centimes > 0)
                .map((row, index) => (
                  <TableRow
                    key={row.teacher_id}
                    className="stagger-row"
                    style={{ animationDelay: `${index * 40}ms` }}
                  >
                    <TableCell className="font-medium">
                      {row.teacher_name}
                      {row.is_owner === 1 && (
                        <span className="text-muted-foreground text-xs">
                          {" "}
                          (propriétaire)
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatDH(row.earned_centimes)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatDH(row.paid_centimes)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      <span
                        className={
                          row.remaining_centimes > 0 ? "text-destructive" : ""
                        }
                      >
                        {formatDH(row.remaining_centimes)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {row.payouts.map((payout) => (
                          <ConfirmButton
                            key={payout.id}
                            size="sm"
                            variant="outline"
                            className="h-6 px-2 text-xs"
                            title="Annuler ce versement (erreur de saisie)"
                            confirmLabel="Annuler ce versement ?"
                            description="La ligne disparaît — le reste à verser remonte d'autant."
                            onConfirm={() => cancelPayout(payout.id)}
                          >
                            {formatDH(payout.amount_centimes)} · {payout.paid_on}
                          </ConfirmButton>
                        ))}
                        {row.payouts.length === 0 && (
                          <span className="text-muted-foreground text-xs">—</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      {row.remaining_centimes > 0 && (
                        <PayTeacherButton
                          remaining={row.remaining_centimes}
                          onPay={(amount) => payTeacher(row.teacher_id, amount)}
                        />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              {rows.every(
                (row) => row.earned_centimes === 0 && row.paid_centimes === 0,
              ) && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-muted-foreground text-center"
                  >
                    Aucun professeur n'a encore gagné ce mois-ci
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  )
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: "success" | "alert"
}) {
  const ref = useCountUp(value, (n) => formatDH(Math.round(n)))
  const color =
    tone === "alert" && value > 0
      ? "text-destructive"
      : tone === "success" && value > 0
        ? "text-success"
        : ""
  return (
    <div className="surface-card orb-backdrop p-5">
      <p className="text-muted-foreground text-sm capitalize">{label}</p>
      <p className={`mt-1 text-3xl font-semibold ${color}`}>
        <span ref={ref} />
      </p>
    </div>
  )
}

function Tile({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: number
  hint: string
  tone?: "muted" | "alert"
}) {
  return (
    <div className="border-border rounded-xl border p-4">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p
        className={`text-xl font-semibold ${
          tone === "alert" && value > 0
            ? "text-destructive"
            : tone === "muted"
              ? "text-muted-foreground"
              : ""
        }`}
      >
        {formatDH(value)}
      </p>
      <p className="text-muted-foreground text-xs">{hint}</p>
    </div>
  )
}

/** Tout verser en un clic, ou saisir un acompte. */
function PayTeacherButton({
  remaining,
  onPay,
}: {
  remaining: number
  onPay: (amount?: number) => void
}) {
  const [partial, setPartial] = useState(false)
  const [amount, setAmount] = useState("")

  if (!partial)
    return (
      <span className="flex justify-end gap-1">
        <Button size="sm" onClick={() => onPay()}>
          Tout verser
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setPartial(true)}>
          Acompte
        </Button>
      </span>
    )
  return (
    <span className="flex items-center justify-end gap-1">
      <Input
        autoFocus
        value={amount}
        onChange={(event) => setAmount(event.target.value)}
        placeholder={`≤ ${remaining / 100}`}
        inputMode="decimal"
        className="h-8 w-24 text-right"
      />
      <Button
        size="sm"
        disabled={!amount.trim()}
        onClick={() => {
          onPay(dhToCentimes(amount))
          setPartial(false)
          setAmount("")
        }}
      >
        Verser
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setPartial(false)}>
        ×
      </Button>
    </span>
  )
}
