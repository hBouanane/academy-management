import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { CashBars } from "@/components/charts"
import { MonthNav, monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { apiGet } from "@/lib/api"
import type {
  ArrearsEntry,
  BeneficiaryTotal,
  HistoryEntry,
  MonthlyReport,
} from "@/lib/api"
import { useCountUp, useGrowIn } from "@/lib/anim"
import { formatDH } from "@/lib/money"

const KIND_LABEL: Record<BeneficiaryTotal["kind"], string> = {
  teacher: "Professeur",
  owner: "Propriétaire",
  venue: "Salle",
}

type Props = { month: string; setMonth: (month: string) => void }

export function Reports({ month, setMonth }: Props) {
  const [report, setReport] = useState<MonthlyReport | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [owing, setOwing] = useState<ArrearsEntry[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    apiGet<MonthlyReport>(`/api/reports/monthly?month=${month}`)
      .then(setReport)
      .catch((err: Error) => setError(err.message))
    apiGet<HistoryEntry[]>(`/api/reports/history?up_to_month=${month}&months=6`)
      .then(setHistory)
      .catch(() => setHistory([]))
    apiGet<ArrearsEntry[]>(`/api/reports/arrears?up_to_month=${month}`)
      .then(setOwing)
      .catch(() => setOwing([]))
  }, [month])

  const totalOwed = owing.reduce((sum, entry) => sum + entry.total_owed, 0)
  const teacherTotal = (report?.totals ?? [])
    .filter((total) => total.kind === "teacher")
    .reduce((sum, total) => sum + total.total, 0)

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-medium tracking-tight">Rapports</h2>
          <p className="text-muted-foreground text-sm">
            Qui reçoit quoi — calculé depuis le registre, jamais recalculé
          </p>
        </div>
        <div className="flex items-center gap-2">
          <MonthNav month={month} setMonth={setMonth} />
          <Button asChild variant="outline">
            <a href={`/api/export/monthly.xlsx?month=${month}`} download>
              Exporter Excel
            </a>
          </Button>
        </div>
      </header>

      <Notice message={error} />

      <section className="grid gap-4 lg:grid-cols-3">
        <StatCard
          label={`Encaissé — ${monthLabel(month)}`}
          value={report?.cash_in ?? 0}
        />
        <StatCard label="Reversé aux professeurs" value={teacherTotal} />
        <StatCard label="Impayés cumulés" value={totalOwed} negative />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="surface-card orb-backdrop p-5">
          <p className="text-muted-foreground mb-2 text-sm">
            Encaissements — 6 derniers mois
          </p>
          <CashBars history={history} />
        </div>
        <div className="surface-card p-5">
          <p className="text-muted-foreground mb-3 text-sm">
            Répartition du mois — salle, propriétaire et professeurs
          </p>
          <BeneficiaryBars totals={report?.totals ?? []} />
        </div>
      </div>

      {report?.by_level.map((level) => (
        <div key={level.level_id} className="surface-card p-5">
          <h3 className="mb-3 font-medium">{level.level_name}</h3>
          <TotalsTable totals={level.totals} />
        </div>
      ))}

      <div className="surface-card p-5">
        <h3 className="font-medium">Impayés (jusqu'à {monthLabel(month)})</h3>
        <p className="text-muted-foreground mb-3 text-sm">
          Étudiants qui doivent encore de l'argent
        </p>
        <div className="table-wrap">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Étudiant</TableHead>
                <TableHead>Niveau</TableHead>
                <TableHead>Mois dus</TableHead>
                <TableHead className="text-right">Total dû</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {owing.map((entry, index) => (
                <TableRow
                  key={entry.student_id}
                  className="stagger-row row-unpaid"
                  style={{ animationDelay: `${index * 40}ms` }}
                >
                  <TableCell className="font-medium">
                    {entry.student_name}
                  </TableCell>
                  <TableCell>{entry.level_name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {entry.items
                      .map((item) => `${item.month} (${formatDH(item.owed)})`)
                      .join(", ")}
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    {formatDH(entry.total_owed)}
                  </TableCell>
                </TableRow>
              ))}
              {owing.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={4}
                    className="text-muted-foreground text-center"
                  >
                    Personne ne doit rien 🎉
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
  negative = false,
}: {
  label: string
  value: number
  negative?: boolean
}) {
  const ref = useCountUp(value, (n) => formatDH(Math.round(n)))
  return (
    <div className="surface-card orb-backdrop p-5">
      <p className="text-muted-foreground text-sm capitalize">{label}</p>
      <p
        className={`mt-1 text-3xl font-semibold ${
          negative && value > 0 ? "text-destructive" : ""
        }`}
      >
        <span ref={ref} />
      </p>
    </div>
  )
}

/** Horizontal bars: every beneficiary of the month, grown in with GSAP. */
function BeneficiaryBars({ totals }: { totals: BeneficiaryTotal[] }) {
  const ref = useGrowIn<HTMLDivElement>([totals], "x")
  const max = Math.max(...totals.map((total) => Math.abs(total.total)), 1)
  if (totals.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">Aucun paiement ce mois</p>
    )
  }
  return (
    <div ref={ref} className="space-y-2.5">
      {totals.map((total) => (
        <div key={`${total.kind}-${total.ref_id}`} className="text-sm">
          <div className="mb-0.5 flex items-center justify-between gap-2">
            <span className="truncate">
              {total.name}{" "}
              <span className="text-muted-foreground text-xs">
                · {KIND_LABEL[total.kind]}
              </span>
            </span>
            <span className={total.total < 0 ? "text-destructive" : "font-medium"}>
              {formatDH(total.total)}
            </span>
          </div>
          <div className="bg-muted h-2 overflow-hidden rounded-full">
            <div
              data-grow
              className="h-full rounded-full"
              style={{
                width: `${(Math.abs(total.total) / max) * 100}%`,
                background:
                  total.total < 0 ? "var(--destructive)" : "var(--chart-mark)",
                transformOrigin: "left",
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function TotalsTable({ totals }: { totals: BeneficiaryTotal[] }) {
  return (
    <div className="table-wrap">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Bénéficiaire</TableHead>
            <TableHead>Rôle</TableHead>
            <TableHead className="text-right">Montant</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {totals.map((total, index) => (
            <TableRow
              key={`${total.kind}-${total.ref_id}`}
              className="stagger-row"
              style={{ animationDelay: `${index * 40}ms` }}
            >
              <TableCell className="font-medium">{total.name}</TableCell>
              <TableCell>
                <Badge variant="outline">{KIND_LABEL[total.kind]}</Badge>
              </TableCell>
              <TableCell className="text-right">{formatDH(total.total)}</TableCell>
            </TableRow>
          ))}
          {totals.length === 0 && (
            <TableRow>
              <TableCell colSpan={3} className="text-muted-foreground text-center">
                Aucun paiement ce mois
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
