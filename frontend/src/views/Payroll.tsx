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
import { GuaranteeDialog } from "@/components/GuaranteeDialog"
import { MonthNav, monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { PayDialog } from "@/components/PayDialog"
import { StudentProfile } from "@/components/StudentProfile"
import { TeacherProfile } from "@/components/TeacherProfile"
import { apiGet, apiSend } from "@/lib/api"
import type { Academy, OverviewRow, PayoutRow } from "@/lib/api"
import { useCountUp } from "@/lib/anim"
import { currentMonth, dhToCentimes, formatDH, previousMonth } from "@/lib/money"

export function Payroll() {
  // La paie se fait sur le mois ÉCOULÉ : le mois en cours n'est pas fini,
  // alors que les étudiants, eux, paient au début du leur. Cette page a donc
  // son propre mois, indépendant du reste de l'application.
  const [month, setMonth] = useState(() => previousMonth(currentMonth()))
  const [rows, setRows] = useState<PayoutRow[]>([])
  const [overview, setOverview] = useState<OverviewRow[]>([])
  const [academy, setAcademy] = useState<Academy | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Encaisser un impayé, solder un professeur, ouvrir un profil — sans
  // quitter la page.
  const [payTarget, setPayTarget] = useState<{ id: number; name: string } | null>(
    null,
  )
  const [guaranteeTarget, setGuaranteeTarget] = useState<{
    id: number
    name: string
  } | null>(null)
  const [studentProfile, setStudentProfile] = useState<number | null>(null)
  const [teacherProfile, setTeacherProfile] = useState<number | null>(null)

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

  const due = rows.reduce((sum, row) => sum + row.due_centimes, 0)
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
        <div className="flex flex-wrap items-center gap-2">
          {month !== currentMonth() && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setMonth(currentMonth())}
            >
              Mois en cours
            </Button>
          )}
          <MonthNav month={month} setMonth={setMonth} />
        </div>
      </header>

      {month === previousMonth(currentMonth()) && (
        <p className="text-muted-foreground text-xs">
          Mois écoulé par défaut : les professeurs se paient sur un mois
          terminé, alors que les étudiants paient au début du leur.
        </p>
      )}

      <Notice message={error} />

      <section className="grid gap-4 lg:grid-cols-3">
        <StatCard
          label={`Dû aux professeurs — ${monthLabel(month)}`}
          value={due}
          hint="sur les élèves inscrits, payés ou non"
        />
        <StatCard
          label="Déjà versé"
          value={paid}
          tone="success"
          hint="ce que vous leur avez réellement remis"
        />
        <StatCard
          label="Reste à verser"
          value={remaining}
          tone="alert"
          hint="dû moins versé"
        />
      </section>

      <div className="surface-card p-5">
        <h3 className="font-medium">Ce que les impayés vous coûtent</h3>
        <p className="text-muted-foreground mb-4 text-sm">
          La salle et l'académie ne touchent que sur les élèves qui paient —
          leur part d'un impayé n'est jamais encaissée. La part du professeur,
          elle, sort de votre poche : il est payé quoi qu'il arrive.
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
                ? `de votre poche · ${formatDH(guaranteed)} déjà soldé`
                : "de votre poche"
            }
            tone="alert"
          />
        </div>

        {unpaid.length > 0 && (
          <div className="table-wrap mt-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Élève impayé</TableHead>
                  <TableHead className="text-right">Doit</TableHead>
                  <TableHead className="text-right">
                    Part professeur
                  </TableHead>
                  <TableHead>État</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {unpaid.map((row, index) => {
                  const enrollment = row.enrollment!
                  const teacherPart = enrollment.split
                    .filter((chip) => chip.kind === "teacher")
                    .reduce((sum, chip) => sum + chip.final_centimes, 0)
                  return (
                    <TableRow
                      key={row.student_id}
                      className="stagger-row row-unpaid cursor-pointer"
                      style={{ animationDelay: `${index * 40}ms` }}
                      title="Ouvrir le profil"
                      onClick={(event) => {
                        const target = event.target as HTMLElement
                        if (!event.currentTarget.contains(target)) return
                        if (target.closest("button, a")) return
                        setStudentProfile(row.student_id)
                      }}
                    >
                      <TableCell className="font-medium">
                        {row.student_name}
                        <span className="text-muted-foreground text-xs">
                          {" "}
                          · {row.level_name}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        {formatDH(enrollment.net_centimes)}
                      </TableCell>
                      <TableCell className="text-right">
                        {formatDH(teacherPart)}
                      </TableCell>
                      <TableCell>
                        {enrollment.guaranteed_centimes > 0 ? (
                          <span className="text-success text-xs">
                            prof payé {formatDH(enrollment.guaranteed_centimes)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground text-xs">
                            prof non soldé
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="space-x-1 text-right whitespace-nowrap">
                        <Button
                          size="sm"
                          onClick={() =>
                            setPayTarget({
                              id: enrollment.id,
                              name: row.student_name,
                            })
                          }
                        >
                          Encaisser
                        </Button>
                        {enrollment.guaranteed_centimes === 0 && (
                          <Button
                            size="sm"
                            variant="outline"
                            title="Payer le professeur malgré l'impayé"
                            onClick={() =>
                              setGuaranteeTarget({
                                id: enrollment.id,
                                name: row.student_name,
                              })
                            }
                          >
                            Solder le prof
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <div className="surface-card p-5">
        <h3 className="font-medium">Versements aux professeurs</h3>
        <p className="text-muted-foreground mb-3 text-sm">
          Le dû se calcule sur les élèves inscrits — un professeur est payable
          même si aucun élève n'a encore réglé.
        </p>
        <div className="table-wrap">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Professeur</TableHead>
                <TableHead className="text-right" title="Sur les élèves inscrits du mois, payés ou non">
                  Dû
                </TableHead>
                <TableHead className="text-right">Versé</TableHead>
                <TableHead className="text-right">Reste</TableHead>
                <TableHead>Versements</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, index) => (
                  <TableRow
                    key={row.teacher_id}
                    className="stagger-row cursor-pointer"
                    style={{ animationDelay: `${index * 40}ms` }}
                    title="Ouvrir le profil du professeur"
                    onClick={(event) => {
                      const target = event.target as HTMLElement
                      if (!event.currentTarget.contains(target)) return
                      if (target.closest("button, a, input")) return
                      setTeacherProfile(row.teacher_id)
                    }}
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
                      {formatDH(row.due_centimes)}
                      {row.collected_centimes < row.due_centimes && (
                        <p
                          className="text-muted-foreground text-xs"
                          title="Part réellement encaissée auprès de ses élèves"
                        >
                          dont {formatDH(row.collected_centimes)} encaissé
                        </p>
                      )}
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
                      {row.remaining_centimes > 0 ? (
                        <PayTeacherButton
                          remaining={row.remaining_centimes}
                          onPay={(amount) => payTeacher(row.teacher_id, amount)}
                        />
                      ) : row.due_centimes > 0 ? (
                        <span className="text-success text-xs">Soldé ✓</span>
                      ) : (
                        <span className="text-muted-foreground text-xs">
                          aucun élève ce mois
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              {rows.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-muted-foreground text-center"
                  >
                    Aucun professeur
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

      {guaranteeTarget && (
        <GuaranteeDialog
          enrollmentId={guaranteeTarget.id}
          studentName={guaranteeTarget.name}
          month={month}
          onClose={() => setGuaranteeTarget(null)}
          onDone={() => {
            setGuaranteeTarget(null)
            reload()
          }}
        />
      )}

      <StudentProfile
        studentId={studentProfile}
        onClose={() => setStudentProfile(null)}
        onChanged={reload}
      />

      <TeacherProfile
        teacherId={teacherProfile}
        month={month}
        onClose={() => setTeacherProfile(null)}
        onChanged={reload}
      />
    </div>
  )
}

function StatCard({
  label,
  value,
  tone,
  hint,
}: {
  label: string
  value: number
  tone?: "success" | "alert"
  hint?: string
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
      {hint && <p className="text-muted-foreground mt-1 text-xs">{hint}</p>}
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
