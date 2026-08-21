// The guided departure: a teacher who still teaches cannot just vanish.
// Every class he holds gets an explicit fate -- bulk-selectable:
//   Remplacer            -> dated handover, the money follows the days;
//   Sans professeur      -> the class survives, loudly vacant, escrow to
//                          l'academie until someone is named;
//   Archiver la classe   -> no teacher will come: students leave it, paid
//                          ones get their refund percentage.
// Only then is the teacher archived.

import { useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Notice } from "@/components/Notice"
import {
  affectedStudents,
  RefundForEveryone,
  RefundPicker,
} from "@/components/ArchiveClassDialog"
import type { AffectedStudent } from "@/components/ArchiveClassDialog"
import { apiGet, apiSend } from "@/lib/api"
import type { ClassRow, OverviewRow, Teacher } from "@/lib/api"
import { segmentLabel } from "@/lib/levels"
import { currentMonth } from "@/lib/money"
import { useAlert } from "@/lib/alert"
import { useToast } from "@/components/Toast"

const todayIso = () => {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  return `${now.getFullYear()}-${month}-${String(now.getDate()).padStart(2, "0")}`
}

type Action = "replace" | "vacate" | "archive"

const ACTION_LABEL: Record<Action, string> = {
  replace: "Remplacer",
  vacate: "Sans professeur",
  archive: "Archiver la classe",
}

type Decision = { action: Action; successorId: number | null }

export function ArchiveTeacherDialog({
  teacher,
  teachers,
  onClose,
  onDone,
}: {
  teacher: Teacher
  teachers: Teacher[]
  onClose: () => void
  onDone: () => void
}) {
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [overview, setOverview] = useState<OverviewRow[]>([])
  const [date, setDate] = useState(todayIso())
  const [decisions, setDecisions] = useState<Record<number, Decision>>({})
  const [percents, setPercents] = useState<Record<number, number>>({})
  const [checked, setChecked] = useState<Set<number>>(new Set())
  const [bulkAction, setBulkAction] = useState<Action>("replace")
  const [bulkSuccessor, setBulkSuccessor] = useState<string>("")
  const [note, setNote] = useAlert()
  const [busy, setBusy] = useState(false)
  // The rows just changed in bulk: they light up for a second,
  // otherwise you click without knowing whether anything moved.
  const [justApplied, setJustApplied] = useState<Set<number>>(new Set())
  const toast = useToast()

  useEffect(() => {
    if (justApplied.size === 0) return
    const timer = window.setTimeout(() => setJustApplied(new Set()), 1200)
    return () => window.clearTimeout(timer)
  }, [justApplied])

  useEffect(() => {
    apiGet<ClassRow[]>(`/api/classes?month=${currentMonth()}`)
      .then((rows) => {
        const his = rows.filter(
          (row) => row.is_active === 1 && row.teacher_id === teacher.id,
        )
        setClasses(his)
        setDecisions(
          Object.fromEntries(
            his.map((row) => [row.id, { action: "replace", successorId: null }]),
          ),
        )
      })
      .catch((err: Error) => setNote(err.message))
    apiGet<OverviewRow[]>(`/api/months/${currentMonth()}/overview`)
      .then(setOverview)
      .catch(() => {})
  }, [teacher.id, setNote])

  const successors = teachers.filter(
    (candidate) => candidate.id !== teacher.id,
  )
  const affectedByClass = useMemo(() => {
    const map: Record<number, AffectedStudent[]> = {}
    for (const row of classes)
      map[row.id] = affectedStudents(overview, row.id)
    return map
  }, [classes, overview])

  const setDecision = (classId: number, patch: Partial<Decision>) => {
    setDecisions((current) => ({
      ...current,
      [classId]: { ...current[classId], ...patch },
    }))
    if (patch.action === "archive") {
      // Paid students of that class default to a full refund — visible,
      // adjustable, never silent.
      for (const student of (affectedByClass[classId] ?? []).filter(
        (entry) => entry.paid,
      ))
        setPercents((current) => ({
          ...current,
          [student.enrollmentId]: current[student.enrollmentId] ?? 100,
        }))
    }
  }

  /** What the button will do, spelled out -- « Appliquer » said neither
      to what nor to how many. */
  const bulkSummary = () => {
    const many = `${checked.size} classe${checked.size > 1 ? "s" : ""}`
    if (bulkAction === "vacate") return `Laisser ${many} sans professeur`
    if (bulkAction === "archive") return `Archiver ${many}`
    const successor = successors.find(
      (candidate) => String(candidate.id) === bulkSuccessor,
    )
    return successor
      ? `Confier ${many} à ${successor.name}`
      : "Choisissez d'abord le successeur"
  }
  const bulkReady = bulkAction !== "replace" || bulkSuccessor !== ""

  const applyBulk = () => {
    const touched = new Set(checked)
    for (const classId of touched)
      setDecision(classId, {
        action: bulkAction,
        successorId: bulkSuccessor ? Number(bulkSuccessor) : null,
      })
    // The selection has served its purpose: we release it, otherwise the
    // next gesture would start again on the same rows unintentionally.
    setChecked(new Set())
    setJustApplied(touched)
    toast(bulkSummary())
  }

  /** The common case: somebody takes over EVERYTHING he was teaching. */
  const handEverythingTo = (successorId: number) => {
    for (const row of classes)
      setDecision(row.id, { action: "replace", successorId })
    setChecked(new Set(classes.map((row) => row.id)))
  }
  const everythingTo =
    classes.length > 0 &&
    classes.every(
      (row) =>
        decisions[row.id]?.action === "replace" &&
        decisions[row.id]?.successorId !== null &&
        decisions[row.id]?.successorId === decisions[classes[0].id]?.successorId,
    )
      ? decisions[classes[0].id].successorId
      : null

  const problems = classes.filter(
    (row) =>
      decisions[row.id]?.action === "replace" &&
      decisions[row.id]?.successorId === null,
  )

  const execute = async () => {
    if (problems.length > 0) {
      setNote(
        "Chaque classe « Remplacer » doit avoir un successeur — sinon" +
          " choisissez « Sans professeur » ou « Archiver la classe ».",
      )
      return
    }
    setNote(null)
    setBusy(true)
    try {
      for (const row of classes) {
        const decision = decisions[row.id]
        if (decision.action === "replace") {
          await apiSend("POST", `/api/classes/${row.id}/replace-teacher`, {
            date,
            successor_id: decision.successorId,
          })
        } else if (decision.action === "vacate") {
          await apiSend("POST", `/api/classes/${row.id}/vacate-teacher`, { date })
        } else {
          const paid = (affectedByClass[row.id] ?? []).filter(
            (student) => student.paid,
          )
          await apiSend("POST", `/api/classes/${row.id}/archive`, {
            date,
            refunds: paid.map((student) => ({
              enrollment_id: student.enrollmentId,
              percent_bp: (percents[student.enrollmentId] ?? 0) * 100,
            })),
          })
        }
      }
      await apiSend("PATCH", `/api/teachers/${teacher.id}`, { is_active: false })
      onDone()
    } catch (err) {
      setNote((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Archiver {teacher.name}</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          Il enseigne encore {classes.length} classe(s) — décidez le sort de
          chacune. Il reste payé jusqu'à la veille de la date choisie, et ses
          anciens mois continueront de lui revenir quand ils seront encaissés.
        </p>
        <div className="space-y-4">
          {/* The commonest case in one gesture: somebody takes it all.
              Otherwise each class keeps its own decision below. */}
          {classes.length > 0 && successors.length > 0 && (
            <div className="border-border flex flex-wrap items-center gap-2 rounded-xl border border-dashed p-3">
              <span className="text-sm font-medium">
                Tout confier à un seul professeur
              </span>
              <Select
                value={everythingTo === null ? "" : String(everythingTo)}
                onValueChange={(value) => handEverythingTo(Number(value))}
              >
                <SelectTrigger className="h-8 w-48 text-xs">
                  <SelectValue placeholder="Choisir le successeur…" />
                </SelectTrigger>
                <SelectContent>
                  {successors.map((candidate) => (
                    <SelectItem key={candidate.id} value={String(candidate.id)}>
                      {candidate.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-muted-foreground text-xs">
                il reprend les {classes.length} classe(s) — ajustez ensuite
                celles qui font exception
              </span>
            </div>
          )}
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-2">
              <Label>Date de départ</Label>
              <Input
                type="date"
                value={date}
                onChange={(event) => setDate(event.target.value)}
                className="w-44"
              />
            </div>
          </div>

          {classes.length > 1 && (
            <label className="text-muted-foreground flex items-center gap-2 text-xs">
              <Checkbox
                checked={checked.size === classes.length && classes.length > 0}
                onCheckedChange={(state) =>
                  setChecked(
                    state === true
                      ? new Set(classes.map((row) => row.id))
                      : new Set(),
                  )
                }
              />
              Tout sélectionner
            </label>
          )}

          {/* The bar appears only when there is something to act on, and
              it says what it will do: « Appliquer » said neither to what
              nor to how many. Once done, the selection is released. */}
          {classes.length > 1 && checked.size > 0 && (
            <div className="border-primary/40 bg-primary/5 flex flex-wrap items-center gap-2 rounded-xl border p-2.5">
              <span className="text-sm font-medium">
                {checked.size} classe{checked.size > 1 ? "s" : ""} sélectionnée
                {checked.size > 1 ? "s" : ""}
              </span>
              <Select
                value={bulkAction}
                onValueChange={(value) => setBulkAction(value as Action)}
              >
                <SelectTrigger className="h-8 w-40 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(ACTION_LABEL) as Action[]).map((action) => (
                    <SelectItem key={action} value={action}>
                      {ACTION_LABEL[action]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {bulkAction === "replace" && (
                <Select value={bulkSuccessor} onValueChange={setBulkSuccessor}>
                  <SelectTrigger className="h-8 w-40 text-xs">
                    <SelectValue placeholder="Successeur…" />
                  </SelectTrigger>
                  <SelectContent>
                    {successors.map((candidate) => (
                      <SelectItem key={candidate.id} value={String(candidate.id)}>
                        {candidate.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <Button size="sm" disabled={!bulkReady} onClick={applyBulk}>
                {bulkSummary()}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setChecked(new Set())}
              >
                Tout désélectionner
              </Button>
            </div>
          )}

          <div className="space-y-3">
            {classes.map((row) => {
              const decision = decisions[row.id] ?? {
                action: "replace" as Action,
                successorId: null,
              }
              const paid = (affectedByClass[row.id] ?? []).filter(
                (student) => student.paid,
              )
              const unpaid = (affectedByClass[row.id] ?? []).filter(
                (student) => !student.paid,
              )
              const picked = checked.has(row.id)
              return (
                <div
                  key={row.id}
                  className={`rounded-xl border p-3 transition-colors ${
                    picked
                      ? "border-primary bg-primary/5"
                      : "border-border"
                  } ${justApplied.has(row.id) ? "row-applied" : ""}`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {classes.length > 1 && (
                      <Checkbox
                        checked={picked}
                        onCheckedChange={(state) =>
                          setChecked((current) => {
                            const next = new Set(current)
                            if (state === true) next.add(row.id)
                            else next.delete(row.id)
                            return next
                          })
                        }
                      />
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="font-medium">{row.subject_name}</span>
                      <span className="text-muted-foreground text-xs">
                        {" "}
                        · {segmentLabel(row)} · {row.enrolled_count ?? 0} inscrit(s)
                      </span>
                    </span>
                    <Select
                      value={decision.action}
                      onValueChange={(value) =>
                        setDecision(row.id, { action: value as Action })
                      }
                    >
                      <SelectTrigger className="h-8 w-44 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(Object.keys(ACTION_LABEL) as Action[]).map((action) => (
                          <SelectItem key={action} value={action}>
                            {ACTION_LABEL[action]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {decision.action === "replace" && (
                      <Select
                        value={
                          decision.successorId === null
                            ? ""
                            : String(decision.successorId)
                        }
                        onValueChange={(value) =>
                          setDecision(row.id, { successorId: Number(value) })
                        }
                      >
                        <SelectTrigger className="h-8 w-40 text-xs">
                          <SelectValue placeholder="Successeur…" />
                        </SelectTrigger>
                        <SelectContent>
                          {successors.map((candidate) => (
                            <SelectItem
                              key={candidate.id}
                              value={String(candidate.id)}
                            >
                              {candidate.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                  {decision.action === "archive" && paid.length > 0 && (
                    <div className="mt-3 space-y-2 border-t pt-3">
                      <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                        Remboursements (ont payé)
                      </p>
                      {paid.length > 1 && (
                        <RefundForEveryone
                          count={paid.length}
                          onApply={(percent) =>
                            setPercents((current) => ({
                              ...current,
                              ...Object.fromEntries(
                                paid.map((student) => [
                                  student.enrollmentId,
                                  percent,
                                ]),
                              ),
                            }))
                          }
                        />
                      )}
                      {paid.map((student) => (
                        <RefundPicker
                          key={student.enrollmentId}
                          student={student}
                          percent={percents[student.enrollmentId] ?? 100}
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
                  {decision.action === "archive" && unpaid.length > 0 && (
                    <p className="text-muted-foreground mt-2 text-xs">
                      Désinscrits sans remboursement (impayés) :{" "}
                      {unpaid.map((student) => student.studentName).join(", ")}
                    </p>
                  )}
                </div>
              )
            })}
            {classes.length === 0 && (
              <p className="text-muted-foreground text-sm">
                Aucune classe active — l'archivage est direct.
              </p>
            )}
          </div>

          <Notice alert={note} />
        </div>
        <DialogFooter>
          <Button variant="destructive" onClick={execute} disabled={busy}>
            {busy ? "…" : "Exécuter puis archiver le professeur"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
