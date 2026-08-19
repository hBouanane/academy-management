// Archiving a class is a real event: current-month students leave it. Those
// who PAID get a refund promise at the percentage chosen here — a percentage
// of what they actually paid (net of reductions), never of the list price.
// An impayé gets no money back: he never paid.

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import type { ClassRow, OverviewRow } from "@/lib/api"
import { currentMonth, formatDH } from "@/lib/money"
import { useAlert } from "@/lib/alert"
import { useToast } from "@/components/Toast"

const todayIso = () => {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  return `${now.getFullYear()}-${month}-${String(now.getDate()).padStart(2, "0")}`
}

export type AffectedStudent = {
  enrollmentId: number
  studentName: string
  paid: boolean
  // Estimated slice of what he actually paid for THIS class (the backend
  // computes the exact amount: cash received ÷ classes, largest remainder).
  sliceCentimes: number
}

export function affectedStudents(
  rows: OverviewRow[],
  classId: number,
): AffectedStudent[] {
  return rows
    .filter((row) =>
      row.enrollment?.classes.some((entry) => entry.id === classId),
    )
    .map((row) => {
      const enrollment = row.enrollment!
      const cash = enrollment.paid
        ? enrollment.net_centimes - enrollment.remaining_centimes
        : 0
      return {
        enrollmentId: enrollment.id,
        studentName: row.student_name,
        paid: enrollment.paid,
        sliceCentimes: Math.floor(cash / Math.max(enrollment.classes.length, 1)),
      }
    })
}

const PERCENT_CHOICES = [100, 70, 50, 0]

/** Un seul geste pour tout le monde — le cas courant. Chaque élève reste
    ajustable ensuite pour les exceptions. */
export function RefundForEveryone({
  count,
  onApply,
}: {
  count: number
  onApply: (percent: number) => void
}) {
  const [custom, setCustom] = useState("")
  // Ce qu'on vient d'appliquer reste marqué : sans ça, on clique un
  // pourcentage et rien ne dit qu'il a pris.
  const [applied, setApplied] = useState<number | null>(null)
  const toast = useToast()

  const apply = (percent: number) => {
    onApply(percent)
    setApplied(percent)
    toast(`${percent} % pour les ${count} élèves qui ont payé`)
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 text-sm">
      <span className="text-muted-foreground mr-1 text-xs">
        Appliquer à tous ({count}) :
      </span>
      {PERCENT_CHOICES.map((choice) => (
        <button
          key={choice}
          type="button"
          onClick={() => apply(choice)}
          className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
            applied === choice
              ? "border-transparent bg-primary text-primary-foreground font-medium"
              : "border-border hover:border-foreground/40"
          }`}
        >
          {choice}%
        </button>
      ))}
      <Input
        value={custom}
        onChange={(event) => setCustom(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== "Enter") return
          event.preventDefault()
          const value = Number(custom)
          if (Number.isFinite(value))
            apply(Math.max(0, Math.min(100, Math.round(value))))
        }}
        placeholder="%"
        className="h-7 w-14 text-center text-xs"
        inputMode="numeric"
      />
    </div>
  )
}

export function RefundPicker({
  student,
  percent,
  onChange,
}: {
  student: AffectedStudent
  percent: number
  onChange: (percent: number) => void
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
      <span className="min-w-0">
        <span className="font-medium">{student.studentName}</span>
        <span className="text-muted-foreground text-xs">
          {" "}
          — a payé ≈ {formatDH(student.sliceCentimes)} pour cette classe
        </span>
      </span>
      <span className="flex items-center gap-1">
        {PERCENT_CHOICES.map((choice) => (
          <button
            key={choice}
            type="button"
            onClick={() => onChange(choice)}
            className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
              percent === choice
                ? "border-transparent bg-primary text-primary-foreground"
                : "border-border text-muted-foreground hover:border-foreground/40"
            }`}
          >
            {choice}%
          </button>
        ))}
        <Input
          value={String(percent)}
          onChange={(event) => {
            const value = Number(event.target.value)
            if (Number.isFinite(value))
              onChange(Math.max(0, Math.min(100, Math.round(value))))
          }}
          className="h-7 w-14 text-center text-xs"
          inputMode="numeric"
        />
        <span className="text-muted-foreground w-20 text-right text-xs">
          ≈ {formatDH(Math.floor((student.sliceCentimes * percent) / 100))}
        </span>
      </span>
    </div>
  )
}

export function ArchiveClassDialog({
  target,
  onClose,
  onDone,
}: {
  target: ClassRow
  onClose: () => void
  onDone: () => void
}) {
  const [date, setDate] = useState(todayIso())
  const [affected, setAffected] = useState<AffectedStudent[]>([])
  const [percents, setPercents] = useState<Record<number, number>>({})
  const [note, setNote] = useAlert()
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    apiGet<OverviewRow[]>(`/api/months/${currentMonth()}/overview`)
      .then((rows) => {
        const students = affectedStudents(rows, target.id)
        setAffected(students)
        setPercents(
          Object.fromEntries(
            students
              .filter((student) => student.paid)
              .map((student) => [student.enrollmentId, 100]),
          ),
        )
      })
      .catch((err: Error) => setNote(err.message))
  }, [target.id, setNote])

  const paid = affected.filter((student) => student.paid)
  const unpaid = affected.filter((student) => !student.paid)

  const submit = () => {
    setNote(null)
    setBusy(true)
    apiSend("POST", `/api/classes/${target.id}/archive`, {
      date,
      refunds: paid.map((student) => ({
        enrollment_id: student.enrollmentId,
        percent_bp: (percents[student.enrollmentId] ?? 0) * 100,
      })),
    })
      .then(onDone)
      .catch((err: Error) => {
        setNote(err.message)
        setBusy(false)
      })
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            Archiver {target.subject_name}
            {target.teacher_name ? ` · ${target.teacher_name}` : " · Sans professeur"}
          </DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          Les étudiants du mois quittent cette classe. Ceux qui ont payé
          reçoivent une promesse de remboursement — au pourcentage choisi, de ce
          qu'ils ont réellement payé — à retrouver dans « Remboursements »
          (Rapports). Un impayé ne reçoit rien : il n'a rien versé.
        </p>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Date de fin</Label>
            <Input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>

          {paid.length > 0 && (
            <div className="border-border space-y-2 rounded-xl border p-3">
              <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                Remboursements — étudiants ayant payé
              </p>
              {paid.length > 1 && (
                <RefundForEveryone
                  count={paid.length}
                  onApply={(percent) =>
                    setPercents(
                      Object.fromEntries(
                        paid.map((student) => [student.enrollmentId, percent]),
                      ),
                    )
                  }
                />
              )}
              {paid.map((student) => (
                <RefundPicker
                  key={student.enrollmentId}
                  student={student}
                  percent={percents[student.enrollmentId] ?? 0}
                  onChange={(value) =>
                    setPercents((current) => ({
                      ...current,
                      [student.enrollmentId]: value,
                    }))
                  }
                />
              ))}
            </div>
          )}

          {unpaid.length > 0 && (
            <p className="text-muted-foreground text-sm">
              Désinscrits sans remboursement (impayés) :{" "}
              {unpaid.map((student) => student.studentName).join(", ")}
            </p>
          )}
          {affected.length === 0 && (
            <p className="text-muted-foreground text-sm">
              Aucun étudiant ce mois-ci — archivage simple.
            </p>
          )}

          <Notice alert={note} />
        </div>
        <DialogFooter>
          <Button variant="destructive" onClick={submit} disabled={busy}>
            {busy ? "…" : "Archiver la classe"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
