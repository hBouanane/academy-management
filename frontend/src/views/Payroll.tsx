// The month's till: the real money.
//
// A student paying brings money INTO the till -- it lands in nobody's
// pocket. Paying a teacher, the salle or yourself takes it OUT: the owner
// pays himself the way he pays the others.
//
// The division follows the client's rule: the teacher earns on ENROLLED
// students (paid or not), the salle only on money actually collected, and
// the academie takes what is left -- so it absorbs the shortfall. When an
// impayé comes in later, it falls back into ITS month: the salle takes its
// percentage, and all the rest goes to the academie that had fronted it.

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
import { Pagination, usePagination } from "@/components/Pagination"
import { PayoutHistory } from "@/components/PayoutHistory"
import { PayDialog } from "@/components/PayDialog"
import { StudentProfile } from "@/components/StudentProfile"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"
import type { Caisse, CaisseLine, OverviewRow } from "@/lib/api"
import { useCountUp } from "@/lib/anim"
import {
  currentMonth,
  dhToCentimes,
  formatDH,
} from "@/lib/money"
import { useAlert } from "@/lib/alert"
import { openTeacher } from "@/lib/navigation"

const KIND_LABEL: Record<CaisseLine["kind"], string> = {
  venue: "Salle",
  owner: "Académie",
  teacher: "Professeur",
}

export function Payroll() {
  // Opens on the CURRENT month, like every other screen.
  //
  // It used to open on the elapsed one, reasoning that a running month is
  // not yet settled. But that is not how the day goes: money comes in
  // during the month and teachers get paid during the month, so arriving
  // on a finished month meant stepping forward before doing anything.
  // The page keeps its own month -- he can still walk back to close a
  // month that is over.
  const [month, setMonth] = useState(() => currentMonth())
  const [caisse, setCaisse] = useState<Caisse | null>(null)
  const [overview, setOverview] = useState<OverviewRow[]>([])
  const [error, setError] = useAlert()
  // Collect an impayé, settle a teacher, open a profile -- without
  // leaving the page.
  const [payTarget, setPayTarget] = useState<{
    id: number
    name: string
  } | null>(null)
  const [guaranteeTarget, setGuaranteeTarget] = useState<{
    id: number
    name: string
  } | null>(null)
  const [studentProfile, setStudentProfile] = useState<number | null>(null)
  const toast = useToast()
  const reload = useCallback(() => {
    setError(null)
    apiGet<Caisse>(`/api/caisse?month=${month}`)
      .then(setCaisse)
      .catch((err: Error) => setError(err.message))
    apiGet<OverviewRow[]>(`/api/months/${month}/overview`)
      .then(setOverview)
      .catch(() => setOverview([]))
  }, [month, setError])
  useEffect(reload, [reload])

  const payOut = (line: CaisseLine, amount?: number) =>
    apiSend<{ id: number; amount_centimes: number }>("POST", "/api/payouts", {
      kind: line.kind,
      ref_id: line.ref_id,
      month,
      ...(amount === undefined ? {} : { amount_centimes: amount }),
    })
      .then((done) => {
        setError(null)
        // The paper to be signed is offered HERE: this is the moment the
        // teacher is standing in front of you, money in hand.
        toast(
          `Versé ${formatDH(done.amount_centimes)} — ${line.name}`,
          "success",
          line.kind === "teacher"
            ? () => printReceipt(done.id)
            : undefined,
          "Imprimer le reçu",
        )
        reload()
      })
      .catch((err: Error) => {
        setError(err.message)
        toast(err.message, "error")
      })

  const takeCharge = (line: CaisseLine) =>
    apiSend<{ amount_centimes: number }>("POST", "/api/overpaid-charges", {
      kind: line.kind,
      ref_id: line.ref_id,
      month,
    })
      .then((done) => {
        setError(null)
        toast(
          `${formatDH(done.amount_centimes)} pris en charge par l'académie —` +
            ` ${line.name} garde la différence`,
        )
        reload()
      })
      .catch((err: Error) => {
        setError(err.message)
        toast(err.message, "error")
      })

  const cancelCharge = (chargeId: number) =>
    apiSend("DELETE", `/api/overpaid-charges/${chargeId}`)
      .then(() => {
        setError(null)
        toast("L'académie ne prend plus ce surplus à sa charge")
        reload()
      })
      .catch((err: Error) => setError(err.message))

  /** Print the receipt that was filed when the money moved.
   *
   * It used to download the file. But it is filed at the moment of paying,
   * so downloading handed him a second copy in his Downloads folder -- two
   * versions of one signed paper, and neither obviously the real one. This
   * sends the filed file to the printer instead.
   */
  const printReceipt = (payoutId: number) =>
    apiSend<{ path: string; printer: string | null }>(
      "POST",
      `/api/payouts/${payoutId}/print`,
    )
      .then((sent) =>
        // Named, not just « sent to the printer ». On a machine whose
        // default is « Microsoft Print to PDF » the document goes to a
        // file and a dialog asks where -- which reads as a fault in the
        // application unless the printer says its own name.
        toast(
          sent.printer
            ? `Envoyé à « ${sent.printer} »`
            : "Envoyé à l'imprimante par défaut",
        ),
      )
      .catch((err: Error) => toast(err.message, "error"))

  const cancelPayout = (payoutId: number) =>
    apiSend("DELETE", `/api/payouts/${payoutId}`)
      .then(() => {
        setError(null)
        toast("Versement annulé — l'argent revient en caisse")
        reload()
      })
      .catch((err: Error) => setError(err.message))

  const lines = caisse?.lines ?? []
  // Beneficiaries grow with the staff, unpaid months grow on their
  // own: two flat lists with nothing to bound them.
  const linesPage = usePagination(lines, 25)
  const stillOwed = lines.reduce(
    (sum, line) => sum + line.remaining_centimes,
    0,
  )
  const unpaid = overview.filter(
    (row) => row.enrollment !== null && !row.enrollment.paid,
  )
  const unpaidPage = usePagination(unpaid, 15)
  // The payouts of one beneficiary, opened on demand: three of them
  // never fitted in a cell.
  const [history, setHistory] = useState<CaisseLine | null>(null)

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-medium tracking-tight">Caisse</h2>
          <p className="text-muted-foreground text-sm">
            L'argent du mois : ce qui est entré, ce qui en est sorti, et la part
            qui revient encore à chacun
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

      <Notice alert={error} />

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
                <TableHead>Pour qui</TableHead>
                <TableHead className="text-right">Part du mois</TableHead>
                <TableHead className="text-right">Sorti</TableHead>
                <TableHead className="text-right">Reste à sortir</TableHead>
                <TableHead>Versements</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {linesPage.visible.map((line, index) => (
                <TableRow
                  key={`${line.kind}-${line.ref_id}`}
                  className={`stagger-row ${
                    line.overpaid_centimes > 0 ||
                    line.previous_overpaid_centimes > 0
                      ? "row-attention"
                      : ""
                  } ${line.kind === "teacher" ? "cursor-pointer" : ""}`}
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
                    openTeacher(line.ref_id)
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
                      className={
                        line.due_centimes < 0 ? "text-destructive" : ""
                      }
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
                    {/* He received more than he was owed: we say so in
                        order to deduct it -- we never claw back on our
                        own. */}
                    {line.overpaid_centimes > 0 && (
                      <div className="flex flex-col items-end gap-0.5">
                        <p
                          className="text-destructive text-xs"
                          title="Une réduction ou un remboursement est passé après le versement"
                        >
                          payé en trop {formatDH(line.overpaid_centimes)}
                        </p>
                        {/* Two outcomes, and he chooses: deduct it later,
                            or absorb it and stop the reminder. */}
                        <ConfirmButton
                          size="sm"
                          variant="ghost"
                          className="h-6 px-2 text-xs"
                          title="L'académie garde ce surplus à sa charge"
                          confirmLabel="L'académie prend à sa charge ?"
                          description={`${line.name} garde ${formatDH(
                            line.overpaid_centimes,
                          )} et plus rien ne sera déduit. La trace reste dans la caisse.`}
                          onConfirm={() => takeCharge(line)}
                        >
                          prendre à ma charge
                        </ConfirmButton>
                      </div>
                    )}
                    {line.charges.map((charge) => (
                      <ConfirmButton
                        key={charge.id}
                        size="sm"
                        variant="ghost"
                        className="text-muted-foreground h-6 px-2 text-xs"
                        title="L'académie a pris ce surplus à sa charge — cliquez pour revenir en arrière"
                        confirmLabel="Ne plus le prendre à sa charge ?"
                        description={`Le rappel de déduire ${formatDH(
                          charge.amount_centimes,
                        )} reviendra sur cette ligne.`}
                        onConfirm={() => cancelCharge(charge.id)}
                      >
                        pris en charge {formatDH(charge.amount_centimes)}
                      </ConfirmButton>
                    ))}
                    {line.previous_overpaid_centimes > 0 && (
                      <p
                        className="text-muted-foreground text-xs"
                        title="Trop-versé des mois précédents — pensez à le déduire"
                      >
                        à déduire {formatDH(line.previous_overpaid_centimes)}
                      </p>
                    )}
                  </TableCell>
                  {/* One line, one summary, and the detail on demand. Three
                      payouts in a cell were three pills carrying an amount, a
                      date, a receipt icon and a cancel action all at once. */}
                  <TableCell>
                    {line.payouts.length === 0 ? (
                      <span className="text-muted-foreground text-xs">—</span>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs"
                        onClick={() => setHistory(line)}
                      >
                        {line.payouts.length}
                        {line.payouts.length > 1 ? " versements" : " versement"}
                        {" · voir"}
                      </Button>
                    )}
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
          <Pagination
            {...linesPage}
            shown={linesPage.visible.length}
            noun="bénéficiaires"
          />
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
                  <TableHead>Élève qui n'a pas payé</TableHead>
                  <TableHead className="text-right">Doit</TableHead>
                  <TableHead className="text-right">Part professeur</TableHead>
                  <TableHead>État</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {unpaidPage.visible.map((row, index) => {
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
                            title="Payer le professeur même si l'élève n'a pas payé"
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
            <Pagination
              {...unpaidPage}
              shown={unpaidPage.visible.length}
              noun="impayés"
            />
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

      {history && (
        <PayoutHistory
          name={history.name}
          payouts={history.payouts}
          canPrint={history.kind === "teacher"}
          onPrint={(payoutId) => printReceipt(payoutId)}
          onCancel={(payoutId) => {
            cancelPayout(payoutId)
            setHistory(null)
          }}
          onClose={() => setHistory(null)}
        />
      )}
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
          Une partie
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
