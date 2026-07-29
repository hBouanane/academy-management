import { useCallback, useEffect, useState } from "react"
import { ChevronLeft, ChevronRight, Lock } from "lucide-react"
import { Badge } from "@/components/ui/badge"
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
import { CashBars, CollectionRing } from "@/components/charts"
import { DiscountDialog } from "@/components/DiscountDialog"
import { EnrollDialog } from "@/components/EnrollDialog"
import { PayDialog } from "@/components/PayDialog"
import { ReverseDialog } from "@/components/ReverseDialog"
import { apiGet, apiSend } from "@/lib/api"
import type { HistoryEntry, MonthlyReport, OverviewRow } from "@/lib/api"
import { useCountUp } from "@/lib/anim"
import { currentMonth, formatDH, previousMonth } from "@/lib/money"

type Props = { month: string; setMonth: (month: string) => void }

function nextMonth(month: string): string {
  const [year, monthNumber] = month.split("-").map(Number)
  const total = year * 12 + (monthNumber - 1) + 1
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`
}

const monthLabel = (month: string) =>
  new Date(`${month}-01T00:00:00`).toLocaleDateString("fr-FR", {
    month: "long",
    year: "numeric",
  })

export function Dashboard({ month, setMonth }: Props) {
  const [rows, setRows] = useState<OverviewRow[]>([])
  const [report, setReport] = useState<MonthlyReport | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [search, setSearch] = useState("")
  const [error, setError] = useState<string | null>(null)

  const locked = month < currentMonth()

  const reload = useCallback(() => {
    setError(null)
    const load = () => {
      apiGet<OverviewRow[]>(`/api/months/${month}/overview`)
        .then(setRows)
        .catch((err: Error) => setError(err.message))
      apiGet<MonthlyReport>(`/api/reports/monthly?month=${month}`)
        .then(setReport)
        .catch(() => setReport(null))
      apiGet<HistoryEntry[]>(`/api/reports/history?up_to_month=${month}&months=6`)
        .then(setHistory)
        .catch(() => setHistory([]))
    }
    // Agenda model: entering an open month silently extends the previous one.
    if (month >= currentMonth()) {
      apiSend("POST", `/api/months/${month}/ensure`)
        .catch(() => {})
        .finally(load)
    } else {
      load()
    }
  }, [month])

  useEffect(reload, [reload])

  const enrolled = rows.filter((row) => row.enrollment)
  const paidCount = enrolled.filter((row) => row.enrollment?.paid).length
  const filtered = rows.filter((row) =>
    row.student_name.toLowerCase().includes(search.trim().toLowerCase()),
  )

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-medium tracking-tight">Tableau de bord</h2>
          <p className="text-muted-foreground text-sm">
            Le mois glisse comme un agenda — le passé est verrouillé, jamais perdu
          </p>
        </div>
        <div className="surface-card flex items-center gap-1 p-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMonth(previousMonth(month))}
            title="Mois précédent"
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="min-w-36 text-center text-sm font-medium capitalize">
            {monthLabel(month)}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMonth(nextMonth(month))}
            title="Mois suivant"
          >
            <ChevronRight className="size-4" />
          </Button>
          {locked && (
            <Badge variant="outline" className="ml-1 gap-1">
              <Lock className="size-3" /> Verrouillé
            </Badge>
          )}
        </div>
      </header>

      {error && (
        <p className="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border p-3 text-sm">
          {error}
        </p>
      )}

      <section className="grid gap-4 lg:grid-cols-3">
        <div className="surface-card orb-backdrop p-5">
          <p className="text-muted-foreground text-sm">
            Encaissé — <span className="capitalize">{monthLabel(month)}</span>
          </p>
          <CountUpAmount value={report?.cash_in ?? 0} />
          <Trend history={history} />
        </div>
        <div className="surface-card flex items-center p-5">
          <CollectionRing paid={paidCount} total={enrolled.length} />
        </div>
        <div className="surface-card p-5">
          <p className="text-muted-foreground mb-2 text-sm">
            Encaissements — 6 derniers mois
          </p>
          <CashBars history={history} />
        </div>
      </section>

      <div className="surface-card p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-medium">Étudiants</h3>
            <p className="text-muted-foreground text-sm">
              {locked
                ? "Mois passé : consultation et encaissement des impayés uniquement"
                : "Inscrire, encaisser, ajuster — l'aperçu montre qui reçoit quoi"}
            </p>
          </div>
          <Input
            placeholder="Rechercher…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="w-56"
          />
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nom</TableHead>
              <TableHead>Matières</TableHead>
              <TableHead>Répartition</TableHead>
              <TableHead className="text-right">À payer</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((row) => (
              <StudentRow
                key={row.student_id}
                row={row}
                month={month}
                locked={locked}
                onDone={reload}
              />
            ))}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="text-muted-foreground text-center"
                >
                  Aucun étudiant ce mois-ci
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function CountUpAmount({ value }: { value: number }) {
  const ref = useCountUp(value, (n) => formatDH(Math.round(n)))
  return (
    <p className="mt-1 text-3xl font-semibold">
      <span ref={ref} />
    </p>
  )
}

function Trend({ history }: { history: HistoryEntry[] }) {
  if (history.length < 2) return <p className="mt-2 h-5" />
  const current = history[history.length - 1].cash_in
  const previous = history[history.length - 2].cash_in
  if (previous === 0)
    return (
      <p className="text-muted-foreground mt-2 text-sm">
        Pas de mois précédent comparable
      </p>
    )
  const delta = ((current - previous) / previous) * 100
  const up = delta >= 0
  return (
    <p className={`mt-2 text-sm ${up ? "text-success" : "text-destructive"}`}>
      {up ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}% vs mois précédent
    </p>
  )
}

function StudentRow({
  row,
  month,
  locked,
  onDone,
}: {
  row: OverviewRow
  month: string
  locked: boolean
  onDone: () => void
}) {
  const enrollment = row.enrollment
  const teacherChips =
    enrollment?.split.filter((chip) => chip.kind === "teacher") ?? []
  return (
    <TableRow>
      <TableCell>
        <p className="font-medium">{row.student_name}</p>
        <p className="text-muted-foreground text-xs">{row.level_name}</p>
      </TableCell>
      <TableCell className="text-muted-foreground">
        {enrollment
          ? enrollment.classes.map((c) => c.subject_name).join(", ")
          : "—"}
      </TableCell>
      <TableCell>
        <div className="flex max-w-64 flex-wrap gap-1">
          {teacherChips.map((chip) => (
            <span
              key={chip.ref_id}
              className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs"
              title={`${chip.name} reçoit ${formatDH(chip.final_centimes)}`}
            >
              {chip.name} · {formatDH(chip.final_centimes)}
            </span>
          ))}
          {enrollment && teacherChips.length === 0 && (
            <span className="text-muted-foreground text-xs">—</span>
          )}
        </div>
      </TableCell>
      <TableCell className="text-right">
        {enrollment ? (
          enrollment.net_centimes !== enrollment.price_centimes ? (
            <span>
              <span className="text-muted-foreground mr-2 text-xs line-through">
                {formatDH(enrollment.price_centimes)}
              </span>
              <span className="font-medium">
                {formatDH(enrollment.net_centimes)}
              </span>
            </span>
          ) : (
            formatDH(enrollment.net_centimes)
          )
        ) : (
          "—"
        )}
      </TableCell>
      <TableCell>
        {!enrollment && <Badge variant="outline">Non inscrit</Badge>}
        {enrollment?.paid && (
          <Badge className="bg-success/15 text-success border-success/20 border">
            Payé
          </Badge>
        )}
        {enrollment && !enrollment.paid && (
          <Badge variant="destructive">Impayé</Badge>
        )}
      </TableCell>
      <TableCell className="space-x-2 text-right">
        {!enrollment && !locked && (
          <EnrollDialog
            studentId={row.student_id}
            studentName={row.student_name}
            levelId={row.level_id}
            month={month}
            onDone={onDone}
          />
        )}
        {enrollment && !enrollment.paid && (
          <>
            {!locked && (
              <DiscountDialog enrollmentId={enrollment.id} onDone={onDone} />
            )}
            <PayDialog
              enrollmentId={enrollment.id}
              studentName={row.student_name}
              onDone={onDone}
            />
          </>
        )}
        {enrollment?.paid && enrollment.payment_id && (
          <ReverseDialog paymentId={enrollment.payment_id} onDone={onDone} />
        )}
      </TableCell>
    </TableRow>
  )
}
