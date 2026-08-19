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
import { ConfirmButton } from "@/components/Confirm"
import { MonthNav, monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { FileDocument } from "@/components/FileDocument"
import { StaleDocuments } from "@/components/StaleDocuments"
import { PayDialog } from "@/components/PayDialog"
import { apiGet, apiSend } from "@/lib/api"
import type {
  ArrearsEntry,
  BeneficiaryTotal,
  HistoryEntry,
  MonthlyReport,
  Refund,
  Teacher,
} from "@/lib/api"
import { useCountUp, useGrowIn } from "@/lib/anim"
import { formatDH } from "@/lib/money"
import { useAlert } from "@/lib/alert"

const KIND_LABEL: Record<BeneficiaryTotal["kind"], string> = {
  teacher: "Professeur",
  owner: "Propriétaire",
  venue: "Salle",
}

type Props = { month: string; setMonth: (month: string) => void }

// Same shape as SQLite's datetime('now'): "YYYY-MM-DD HH:MM:SS" in UTC —
// lexicographic comparison against last_entry_at is then correct.
const utcNow = () => new Date().toISOString().slice(0, 19).replace("T", " ")

export function Reports({ month, setMonth }: Props) {
  const [report, setReport] = useState<MonthlyReport | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [owing, setOwing] = useState<ArrearsEntry[]>([])
  const [refunds, setRefunds] = useState<Refund[]>([])
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [error, setError] = useAlert()
  const [refresh, setRefresh] = useState(0)
  // Collecting an owed month straight from the arrears list.
  const [payTarget, setPayTarget] = useState<{ id: number; name: string } | null>(
    null,
  )
  const [exportedAt, setExportedAt] = useState<string | null>(null)
  const [combined, setCombined] = useState(false)

  useEffect(() => {
    setError(null)
    setExportedAt(localStorage.getItem(`excel-export-${month}`))
    apiGet<MonthlyReport>(`/api/reports/monthly?month=${month}`)
      .then(setReport)
      .catch((err: Error) => setError(err.message))
    apiGet<HistoryEntry[]>(`/api/reports/history?up_to_month=${month}&months=6`)
      .then(setHistory)
      .catch(() => setHistory([]))
    apiGet<ArrearsEntry[]>(`/api/reports/arrears?up_to_month=${month}`)
      .then(setOwing)
      .catch(() => setOwing([]))
    apiGet<Refund[]>("/api/refunds")
      .then(setRefunds)
      .catch(() => setRefunds([]))
    apiGet<Teacher[]>("/api/teachers")
      .then(setTeachers)
      .catch(() => setTeachers([]))
  }, [month, refresh, setError])

  const recordExport = () => {
    const stamp = utcNow()
    localStorage.setItem(`excel-export-${month}`, stamp)
    setExportedAt(stamp)
  }

  // The exported file no longer matches the ledger (e.g. an arrears payment
  // landed on this month after the export).
  const staleExport =
    exportedAt !== null &&
    report?.last_entry_at != null &&
    report.last_entry_at > exportedAt

  const settleRefund = (refund: Refund) =>
    apiSend("POST", `/api/refunds/${refund.id}/settle`)
      .then(() => setRefresh((count) => count + 1))
      .catch((err: Error) => setError(err.message))

  const pendingRefunds = refunds.filter((refund) => refund.status === "pending")
  const totalToRefund = pendingRefunds.reduce(
    (sum, refund) => sum + refund.amount_centimes,
    0,
  )
  const totalOwed = owing.reduce((sum, entry) => sum + entry.total_owed, 0)
  const teacherTotal = (report?.totals ?? [])
    .filter((total) => total.kind === "teacher")
    .reduce((sum, total) => sum + total.total, 0)
  const ownerTeacher = teachers.find((teacher) => teacher.is_owner === 1)
  // Deux casquettes, deux lectures : séparées (qui gagne quoi à quel titre)
  // ou réunies (ce que le propriétaire emporte vraiment). Le bouton bascule
  // de l'une à l'autre, les barres se ré-animent vers leur nouvelle valeur.
  const isOwnerHat = (total: BeneficiaryTotal) =>
    total.kind === "owner" ||
    (total.kind === "teacher" && total.ref_id === ownerTeacher?.id)
  const rawTotals = report?.totals ?? []
  const displayedTotals =
    !combined || !ownerTeacher
      ? rawTotals
      : [
          ...rawTotals
            .filter(isOwnerHat)
            .slice(0, 1)
            .map((total) => ({
              ...total,
              kind: "owner" as const,
              ref_id: ownerTeacher.id,
              name: ownerTeacher.name,
              total: rawTotals
                .filter(isOwnerHat)
                .reduce((sum, entry) => sum + entry.total, 0),
            })),
          ...rawTotals.filter((total) => !isOwnerHat(total)),
        ]

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
          <FileDocument kind="excel" month={month} ready>
            Ranger l'export
          </FileDocument>
          <Button asChild variant="outline">
            <a
              href={`/api/export/monthly.xlsx?month=${month}`}
              download
              onClick={recordExport}
            >
              Enregistrer sous…
            </a>
          </Button>
        </div>
      </header>

      <Notice alert={error} />
      {/* Ce qui a ete range et que les chiffres ont depasse depuis :
          nomme document par document, pas mois par mois. */}
      <StaleDocuments />
      <Notice
        tone="warning"
        message={
          staleExport
            ? `Ce mois a changé depuis votre export Excel — ré-exportez ${monthLabel(
                month,
              )} pour ne pas garder un fichier décalé.`
            : null
        }
      />

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
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-muted-foreground text-sm">
              Répartition du mois — salle, propriétaire et professeurs
            </p>
            {ownerTeacher && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setCombined((current) => !current)}
              >
                {combined
                  ? "Séparer les deux casquettes"
                  : `Réunir ${ownerTeacher.name}`}
              </Button>
            )}
          </div>
          <BeneficiaryBars
            totals={displayedTotals}
            highlight={combined ? ownerTeacher?.id : undefined}
          />
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
                  <TableCell>
                    <div className="flex flex-wrap gap-1.5">
                      {entry.items.map((item) => (
                        <Button
                          key={item.enrollment_id}
                          size="sm"
                          variant="outline"
                          title={`Encaisser ${item.month}`}
                          onClick={() =>
                            setPayTarget({
                              id: item.enrollment_id,
                              name: entry.student_name,
                            })
                          }
                        >
                          {item.month} · {formatDH(item.owed)}
                        </Button>
                      ))}
                    </div>
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

      {refunds.length > 0 && (
        <div className="surface-card p-5">
          <h3 className="font-medium">Remboursements</h3>
          <p className="text-muted-foreground mb-3 text-sm">
            Promis lors de l'archivage d'une classe — l'argent ne bouge dans le
            registre qu'au moment où vous le rendez réellement.
            {totalToRefund > 0 && (
              <>
                {" "}
                Reste à rendre :{" "}
                <span className="text-destructive font-medium">
                  {formatDH(totalToRefund)}
                </span>
              </>
            )}
          </p>
          <div className="table-wrap">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Étudiant</TableHead>
                  <TableHead>Classe</TableHead>
                  <TableHead>Mois</TableHead>
                  <TableHead className="text-right">Montant</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {refunds.map((refund, index) => (
                  <TableRow
                    key={refund.id}
                    className="stagger-row"
                    style={{ animationDelay: `${index * 40}ms` }}
                  >
                    <TableCell className="font-medium">
                      {[refund.first_name, refund.student_name]
                        .filter(Boolean)
                        .join(" ")}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {refund.subject_name} · {refund.level_name}
                    </TableCell>
                    <TableCell className="capitalize">
                      {monthLabel(refund.month)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatDH(refund.amount_centimes)}
                      <span className="text-muted-foreground ml-1 text-xs">
                        ({refund.percent_bp / 100}%)
                      </span>
                    </TableCell>
                    <TableCell>
                      {refund.status === "pending" ? (
                        <Badge variant="destructive">À rembourser</Badge>
                      ) : (
                        <Badge className="bg-success/15 text-success border-success/20 border">
                          Remboursé
                          {refund.settled_at
                            ? ` · ${refund.settled_at.slice(0, 10)}`
                            : ""}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {refund.status === "pending" && (
                        <ConfirmButton
                          size="sm"
                          variant="outline"
                          confirmLabel={`Rendre ${formatDH(refund.amount_centimes)} ?`}
                          description="L'argent sort de la caisse maintenant — repris proportionnellement à ceux qui avaient reçu ce paiement."
                          onConfirm={() => settleRefund(refund)}
                        >
                          Marquer remboursé
                        </ConfirmButton>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

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
            setRefresh((count) => count + 1)
          }}
        />
      )}
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
function BeneficiaryBars({
  totals,
  highlight,
}: {
  totals: BeneficiaryTotal[]
  highlight?: number
}) {
  const ref = useGrowIn<HTMLDivElement>([totals], "x")
  const max = Math.max(...totals.map((total) => Math.abs(total.total)), 1)
  if (totals.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">Aucun paiement ce mois</p>
    )
  }
  return (
    <div ref={ref} className="space-y-2.5">
      {totals.map((total, index) => (
        <div
          key={`${total.kind}-${total.ref_id}`}
          className="stagger-row text-sm"
          style={{ animationDelay: `${index * 50}ms` }}
        >
          <div className="mb-0.5 flex items-center justify-between gap-2">
            <span className="truncate">
              {total.name}{" "}
              <span className="text-muted-foreground text-xs">
                ·{" "}
                {highlight === total.ref_id && total.kind === "owner"
                  ? "propriétaire + professeur"
                  : KIND_LABEL[total.kind]}
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
