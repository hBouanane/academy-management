// La caisse du mois : l'argent réel.
//
// Un élève qui paie fait ENTRER l'argent dans la caisse — il n'atterrit dans
// la poche de personne. Payer un professeur, la salle ou soi-même le fait
// SORTIR : le propriétaire se paie comme il paie les autres.
//
// Le partage suit la règle du client : le professeur touche sur les élèves
// INSCRITS (payés ou non), la salle uniquement sur l'argent réellement
// encaissé, et l'académie prend ce qui reste — donc elle absorbe le manque.
// Quand un impayé rentre plus tard, il retombe dans SON mois : la salle
// prend son pourcentage, tout le reste va à l'académie qui avait avancé.

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
import type { Caisse, CaisseLine, OverviewRow } from "@/lib/api"
import { useCountUp } from "@/lib/anim"
import { currentMonth, dhToCentimes, formatDH, previousMonth } from "@/lib/money"

const KIND_LABEL: Record<CaisseLine["kind"], string> = {
  venue: "Salle",
  owner: "Académie",
  teacher: "Professeur",
}

export function Payroll() {
  // La caisse se solde sur le mois ÉCOULÉ : le mois en cours n'est pas fini,
  // alors que les étudiants, eux, paient au début du leur. Cette page a donc
  // son propre mois, indépendant du reste de l'application.
  const [month, setMonth] = useState(() => previousMonth(currentMonth()))
  const [caisse, setCaisse] = useState<Caisse | null>(null)
  const [overview, setOverview] = useState<OverviewRow[]>([])
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
    apiGet<Caisse>(`/api/caisse?month=${month}`)
      .then(setCaisse)
      .catch((err: Error) => setError(err.message))
    apiGet<OverviewRow[]>(`/api/months/${month}/overview`)
      .then(setOverview)
      .catch(() => setOverview([]))
  }, [month])
  useEffect(reload, [reload])

  const payOut = (line: CaisseLine, amount?: number) =>
    apiSend("POST", "/api/payouts", {
      kind: line.kind,
      ref_id: line.ref_id,
      month,
      ...(amount === undefined ? {} : { amount_centimes: amount }),
    })
      .then(reload)
      .catch((err: Error) => setError(err.message))

  const cancelPayout = (payoutId: number) =>
    apiSend("DELETE", `/api/payouts/${payoutId}`)
      .then(reload)
      .catch((err: Error) => setError(err.message))

  const lines = caisse?.lines ?? []
  const stillOwed = lines.reduce((sum, line) => sum + line.remaining_centimes, 0)
  const unpaid = overview.filter(
    (row) => row.enrollment !== null && !row.enrollment.paid,
  )

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-medium tracking-tight">Caisse</h2>
          <p className="text-muted-foreground text-sm">
            L'argent du mois : ce qui est entré, ce qui en est sorti, et la
            part qui revient encore à chacun
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
          Mois écoulé par défaut : on solde un mois terminé, alors que les
          étudiants paient au début du leur.
        </p>
      )}

      <Notice message={error} />

      <section className="grid gap-4 lg:grid-cols-3">
        <StatCard
          label={`Encaissé — ${monthLabel(month)}`}
          value={caisse?.collected_centimes ?? 0}
          hint="l'argent entré dans la caisse"
        />
        <StatCard
          label="Sorti de la caisse"
          value={caisse?.paid_out_centimes ?? 0}
          tone="success"
          hint="versé aux professeurs, à la salle, à vous"
        />
        <StatCard
          label="Reste en caisse"
          value={caisse?.balance_centimes ?? 0}
          tone={(caisse?.balance_centimes ?? 0) < 0 ? "alert" : undefined}
          hint={
            (caisse?.balance_centimes ?? 0) < 0
              ? "vous avez avancé de votre poche"
              : `dont ${formatDH(stillOwed)} déjà promis`
          }
        />
      </section>

      <div className="surface-card p-5">
        <h3 className="font-medium">La part de chacun</h3>
        <p className="text-muted-foreground mb-3 text-sm">
          Le professeur touche sur les élèves inscrits, payés ou non. La salle
          ne touche que sur l'argent réellement encaissé. L'académie prend ce
          qui reste — c'est elle qui absorbe les impayés. Rien n'appartient à
          personne tant que ce n'est pas sorti de la caisse.
        </p>
        <div className="table-wrap">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Bénéficiaire</TableHead>
                <TableHead className="text-right">Part du mois</TableHead>
                <TableHead className="text-right">Sorti</TableHead>
                <TableHead className="text-right">Reste à sortir</TableHead>
                <TableHead>Versements</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((line, index) => (
                <TableRow
                  key={`${line.kind}-${line.ref_id}`}
                  className={`stagger-row ${line.kind === "teacher" ? "cursor-pointer" : ""}`}
                  style={{ animationDelay: `${index * 40}ms` }}
                  title={
                    line.kind === "teacher"
                      ? "Ouvrir le profil du professeur"
                      : undefined
                  }
                  onClick={(event) => {
                    if (line.kind !== "teacher") return
                    const target = event.target as HTMLElement
                    if (!event.currentTarget.contains(target)) return
                    if (target.closest("button, a, input")) return
                    setTeacherProfile(line.ref_id)
                  }}
                >
                  <TableCell className="font-medium">
                    {line.name}
                    <span className="text-muted-foreground text-xs">
                      {" "}
                      · {KIND_LABEL[line.kind]}
                      {line.is_owner === 1 ? " (vous)" : ""}
                    </span>
                  </TableCell>
                  <TableCell className="text-right">
                    <span
                      className={line.due_centimes < 0 ? "text-destructive" : ""}
                    >
                      {formatDH(line.due_centimes)}
                    </span>
                    {line.due_centimes < 0 && (
                      <p className="text-muted-foreground text-xs">
                        avancé de sa poche
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    {formatDH(line.paid_centimes)}
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    <span
                      className={
                        line.remaining_centimes > 0 ? "text-destructive" : ""
                      }
                    >
                      {formatDH(line.remaining_centimes)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {line.payouts.map((payout) => (
                        <ConfirmButton
                          key={payout.id}
                          size="sm"
                          variant="outline"
                          className="h-6 px-2 text-xs"
                          title="Annuler ce versement (erreur de saisie)"
                          confirmLabel="Annuler ce versement ?"
                          description="L'argent revient dans la caisse et le reste à sortir remonte d'autant."
                          onConfirm={() => cancelPayout(payout.id)}
                        >
                          {formatDH(payout.amount_centimes)} · {payout.paid_on}
                        </ConfirmButton>
                      ))}
                      {line.payouts.length === 0 && (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    {line.remaining_centimes > 0 ? (
                      <PayButton
                        remaining={line.remaining_centimes}
                        onPay={(amount) => payOut(line, amount)}
                      />
                    ) : line.due_centimes > 0 ? (
                      <span className="text-success text-xs">Soldé ✓</span>
                    ) : (
                      <span className="text-muted-foreground text-xs">—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {lines.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-muted-foreground text-center"
                  >
                    Rien à répartir ce mois-ci
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="surface-card p-5">
        <h3 className="font-medium">Ce qui n'est pas encore rentré</h3>
        <p className="text-muted-foreground mb-4 text-sm">
          Les professeurs sont payés quoi qu'il arrive : c'est l'académie qui
          avance. Quand ces élèves régleront, la salle prendra son pourcentage
          et tout le reste reviendra à l'académie.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile
            label={`Impayé — ${monthLabel(month)}`}
            value={caisse?.unpaid_centimes ?? 0}
            hint={`${unpaid.length} élève(s)`}
            tone="alert"
          />
          <Tile
            label="Reviendra à la salle"
            value={caisse?.projection.venue_centimes ?? 0}
            hint="son pourcentage, une fois encaissé"
            tone="muted"
          />
          <Tile
            label="Reviendra à l'académie"
            value={caisse?.projection.owner_centimes ?? 0}
            hint="elle a déjà payé les professeurs"
            tone="muted"
          />
        </div>

        {unpaid.length > 0 && (
          <div className="table-wrap mt-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Élève impayé</TableHead>
                  <TableHead className="text-right">Doit</TableHead>
                  <TableHead className="text-right">Part professeur</TableHead>
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
    tone === "alert" && value !== 0
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

/** Tout sortir en un clic, ou saisir un acompte. */
function PayButton({
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
