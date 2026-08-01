import { useCallback, useEffect, useState } from "react"
import { AlertTriangle, UserRoundX } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
import { ConfirmButton } from "@/components/Confirm"
import { EnrollDialog } from "@/components/EnrollDialog"
import { MonthNav, monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { StudentProfile } from "@/components/StudentProfile"
import { PayDialog } from "@/components/PayDialog"
import { ReverseDialog } from "@/components/ReverseDialog"
import { apiGet, apiSend } from "@/lib/api"
import type { HistoryEntry, MonthlyReport, OverviewRow } from "@/lib/api"
import { useCountUp } from "@/lib/anim"
import { currentMonth, formatDH } from "@/lib/money"

type Props = { month: string; setMonth: (month: string) => void }

export function Dashboard({ month, setMonth }: Props) {
  const [rows, setRows] = useState<OverviewRow[]>([])
  const [report, setReport] = useState<MonthlyReport | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [search, setSearch] = useState("")
  const [error, setError] = useState<string | null>(null)
  // A fresh enrollment chains straight into its pay dialog.
  const [payTarget, setPayTarget] = useState<{ id: number; name: string } | null>(
    null,
  )
  const [profileId, setProfileId] = useState<number | null>(null)
  // Browsing an old month: rows of students who were not enrolled then are
  // noise, so the filter switches itself on (still uncheckable).
  const [enrolledOnly, setEnrolledOnly] = useState(false)
  useEffect(() => {
    setEnrolledOnly(month < currentMonth())
  }, [month])

  const locked = month < currentMonth()
  const future = month > currentMonth()

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
    // Agenda model: only the CURRENT month extends itself silently. Future
    // months are prepared explicitly - browsing ahead must not create data.
    if (month === currentMonth()) {
      apiSend("POST", `/api/months/${month}/ensure`)
        .catch(() => {})
        .finally(load)
    } else {
      load()
    }
  }, [month])

  useEffect(reload, [reload])

  const prepareMonth = () => {
    setError(null)
    apiSend("POST", `/api/months/${month}/ensure`)
      .then(reload)
      .catch((err: Error) => setError(err.message))
  }

  const enrolled = rows.filter((row) => row.enrollment)
  const paidCount = enrolled.filter((row) => row.enrollment?.paid).length
  const filtered = rows.filter(
    (row) =>
      row.student_name.toLowerCase().includes(search.trim().toLowerCase()) &&
      (!enrolledOnly || row.enrollment !== null),
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
        <MonthNav month={month} setMonth={setMonth} />
      </header>

      <Notice message={error} />

      <section className="grid gap-4 lg:grid-cols-3">
        <div className="surface-card orb-backdrop p-5">
          <p className="text-muted-foreground text-sm">
            Encaissé — <span className="capitalize">{monthLabel(month)}</span>
          </p>
          <CountUpAmount value={report?.cash_in ?? 0} />
          <Trend history={history} />
        </div>
        <div className="surface-card orb-backdrop flex items-center p-5">
          <CollectionRing paid={paidCount} total={enrolled.length} />
        </div>
        <div className="surface-card orb-backdrop p-5">
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
                : "Rouge clair = impayé · fond pêche = réduction appliquée"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-muted-foreground flex items-center gap-2 text-sm">
              <Checkbox
                checked={enrolledOnly}
                onCheckedChange={(checked) => setEnrolledOnly(checked === true)}
              />
              Inscrits de ce mois uniquement
            </label>
            {future && (
              <Button variant="outline" size="sm" onClick={prepareMonth}>
                Préparer ce mois
              </Button>
            )}
            <Input
              placeholder="Rechercher…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-56"
            />
          </div>
        </div>
        <div className="table-wrap">
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
              {filtered.map((row, index) => (
                <StudentRow
                  key={row.student_id}
                  row={row}
                  index={index}
                  month={month}
                  locked={locked}
                  onDone={reload}
                  onEnrolled={(id) =>
                    setPayTarget({ id, name: row.student_name })
                  }
                  onShowProfile={setProfileId}
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

      {payTarget && (
        <PayDialog
          enrollmentId={payTarget.id}
          studentName={payTarget.name}
          open
          onOpenChange={(next) => {
            if (!next) setPayTarget(null)
          }}
          onDone={() => {
            setPayTarget(null)
            reload()
          }}
        />
      )}

      <StudentProfile studentId={profileId} onClose={() => setProfileId(null)} />
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
  index,
  month,
  locked,
  onDone,
  onEnrolled,
  onShowProfile,
}: {
  row: OverviewRow
  index: number
  month: string
  locked: boolean
  onDone: () => void
  onEnrolled: (enrollmentId: number) => void
  onShowProfile: (studentId: number) => void
}) {
  const enrollment = row.enrollment
  const reduced =
    enrollment !== null && enrollment.net_centimes !== enrollment.price_centimes
  const unpaid = enrollment !== null && !enrollment.paid
  const rowClass = [
    "stagger-row",
    unpaid ? "row-unpaid" : "",
    reduced ? "row-reduced" : "",
  ]
    .filter(Boolean)
    .join(" ")

  return (
    <TableRow className={rowClass} style={{ animationDelay: `${index * 40}ms` }}>
      <TableCell>
        <button
          className="hover:text-foreground/70 font-medium underline-offset-4 transition-colors hover:underline"
          onClick={() => onShowProfile(row.student_id)}
          title="Ouvrir le profil"
        >
          {row.student_name}
        </button>
        <p className="text-muted-foreground text-xs">{row.level_name}</p>
        {row.has_arrears && (
          <Badge variant="destructive" className="mt-1 gap-1">
            <AlertTriangle className="size-3" /> Impayés antérieurs
          </Badge>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {enrollment
          ? enrollment.classes.map((c) => c.subject_name).join(", ")
          : "—"}
      </TableCell>
      <TableCell>
        <div className="flex max-w-72 flex-wrap gap-1">
          {(enrollment?.split ?? []).map((chip) => (
            <span
              key={`${chip.kind}-${chip.ref_id}`}
              className={`rounded-full px-2 py-0.5 text-xs ${
                chip.final_centimes < 0
                  ? "bg-destructive/10 text-destructive"
                  : "bg-secondary text-secondary-foreground"
              }`}
              title={`${chip.name} reçoit ${formatDH(chip.final_centimes)}`}
            >
              {chip.name} · {formatDH(chip.final_centimes)}
            </span>
          ))}
          {!enrollment && <span className="text-muted-foreground text-xs">—</span>}
        </div>
      </TableCell>
      <TableCell className="text-right">
        {enrollment ? (
          <>
            {reduced ? (
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
            )}
            {enrollment.arrival_date && (
              <p className="text-muted-foreground text-xs">
                prorata — début le{" "}
                {new Date(
                  `${enrollment.arrival_date}T00:00:00`,
                ).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}
              </p>
            )}
          </>
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
        {unpaid && <Badge variant="destructive">Impayé</Badge>}
      </TableCell>
      <TableCell className="space-x-2 text-right">
        {!enrollment && !locked && (
          <EnrollDialog
            studentId={row.student_id}
            studentName={row.student_name}
            levelId={row.level_id}
            month={month}
            onDone={onDone}
            onEnrolled={onEnrolled}
          />
        )}
        {enrollment && unpaid && (
          <>
            <PayDialog
              enrollmentId={enrollment.id}
              studentName={row.student_name}
              onDone={onDone}
            />
            {!locked && (
              <ConfirmButton
                size="sm"
                variant="ghost"
                title="Désinscrire ce mois (aucun paiement enregistré)"
                confirmLabel="Désinscrire ce mois ?"
                description="Aucun paiement n'a été enregistré — la ligne de ce mois sera retirée."
                onConfirm={() =>
                  apiSend("DELETE", `/api/enrollments/${enrollment.id}`)
                    .then(onDone)
                    .catch(() => onDone())
                }
              >
                <UserRoundX className="size-4" />
              </ConfirmButton>
            )}
          </>
        )}
        {enrollment?.paid &&
          enrollment.payment_id &&
          month === currentMonth() && (
            // Only the running month offers reversal: browsing an old month
            // and reversing the wrong payment is a mistake we refuse to invite.
            <ReverseDialog paymentId={enrollment.payment_id} onDone={onDone} />
        )}
      </TableCell>
    </TableRow>
  )
}
