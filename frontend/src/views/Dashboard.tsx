import { useCallback, useEffect, useState } from "react"
import { CopyPlus } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { apiGet, apiSend } from "@/lib/api"
import type { MonthlyReport, OverviewRow } from "@/lib/api"
import { formatDH, previousMonth } from "@/lib/money"
import { DiscountDialog } from "@/components/DiscountDialog"
import { EnrollDialog } from "@/components/EnrollDialog"
import { PayDialog } from "@/components/PayDialog"
import { ReverseDialog } from "@/components/ReverseDialog"

type Props = { month: string; setMonth: (month: string) => void }

export function Dashboard({ month, setMonth }: Props) {
  const [rows, setRows] = useState<OverviewRow[]>([])
  const [report, setReport] = useState<MonthlyReport | null>(null)
  const [search, setSearch] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    setError(null)
    apiGet<OverviewRow[]>(`/api/months/${month}/overview`)
      .then(setRows)
      .catch((err: Error) => setError(err.message))
    apiGet<MonthlyReport>(`/api/reports/monthly?month=${month}`)
      .then(setReport)
      .catch(() => setReport(null))
  }, [month])

  useEffect(reload, [reload])

  const copyLastMonth = () => {
    setError(null)
    setBusy(true)
    apiSend("POST", "/api/months/copy", {
      from_month: previousMonth(month),
      to_month: month,
    })
      .then(reload)
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  const enrolled = rows.filter((row) => row.enrollment)
  const paidCount = enrolled.filter((row) => row.enrollment?.paid).length
  const filtered = rows.filter((row) =>
    row.student_name.toLowerCase().includes(search.trim().toLowerCase()),
  )

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">
            Tableau de bord
          </h2>
          <p className="text-muted-foreground text-sm">
            Inscriptions et encaissements du mois
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Input
            type="month"
            value={month}
            onChange={(event) => {
              if (event.target.value) setMonth(event.target.value)
            }}
            className="w-44"
          />
          <Button variant="outline" onClick={copyLastMonth} disabled={busy}>
            <CopyPlus className="size-4" />
            Copier le mois précédent
          </Button>
        </div>
      </header>

      {error && (
        <p className="border-destructive/40 bg-destructive/10 text-destructive rounded-lg border p-3 text-sm">
          {error}
        </p>
      )}

      <section className="grid gap-4 sm:grid-cols-4">
        <StatCard label="Étudiants actifs" value={String(rows.length)} />
        <StatCard label="Inscrits ce mois" value={String(enrolled.length)} />
        <StatCard
          label="Payé / Impayé"
          value={`${paidCount} / ${enrolled.length - paidCount}`}
        />
        <StatCard
          label="Encaissé"
          value={report ? formatDH(report.cash_in) : "—"}
          accent
        />
      </section>

      <Card className="surface-card">
        <CardHeader>
          <CardTitle>Étudiants — {month}</CardTitle>
          <CardDescription>
            Inscrire, encaisser (avec aperçu de la répartition), corriger
          </CardDescription>
        </CardHeader>
        <div className="space-y-4 px-6 pb-6">
          <Input
            placeholder="Rechercher un étudiant…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="max-w-sm"
          />
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nom</TableHead>
                <TableHead>Niveau</TableHead>
                <TableHead>Matières</TableHead>
                <TableHead className="text-right">À payer</TableHead>
                <TableHead>Statut</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((row) => (
                <StudentRow key={row.student_id} row={row} month={month} onDone={reload} />
              ))}
              {filtered.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-muted-foreground text-center"
                  >
                    Aucun étudiant — créez-en dans la page Étudiants
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  )
}

function StatCard({
  label,
  value,
  accent = false,
}: {
  label: string
  value: string
  accent?: boolean
}) {
  return (
    <Card className="surface-card">
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className={`text-2xl ${accent ? "text-primary" : ""}`}>
          {value}
        </CardTitle>
      </CardHeader>
    </Card>
  )
}

function StudentRow({
  row,
  month,
  onDone,
}: {
  row: OverviewRow
  month: string
  onDone: () => void
}) {
  const enrollment = row.enrollment
  return (
    <TableRow>
      <TableCell className="font-medium">{row.student_name}</TableCell>
      <TableCell>{row.level_name}</TableCell>
      <TableCell className="text-muted-foreground">
        {enrollment
          ? enrollment.classes.map((c) => c.subject_name).join(", ")
          : "—"}
      </TableCell>
      <TableCell className="text-right">
        {enrollment ? formatDH(enrollment.net_centimes) : "—"}
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
        {!enrollment && (
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
            <DiscountDialog enrollmentId={enrollment.id} onDone={onDone} />
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
