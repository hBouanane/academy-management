// One class, its whole story: its slot, who teaches it today, who taught
// it and since when (handovers read at a glance), and the students
// enrolled this month with their payment state.

import { useCallback, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Field, FieldGrid } from "@/components/Field"
import { monthLabel } from "@/components/MonthNav"
import { ClassSplit } from "@/components/ClassSplit"
import { Notice } from "@/components/Notice"
import { Pagination, usePagination } from "@/components/Pagination"
import { apiGet, apiSend } from "@/lib/api"
import type { ClassProfile as Profile, ClassShare } from "@/lib/api"
import { segmentLabel } from "@/lib/levels"
import { useAlert } from "@/lib/alert"

type Props = {
  classId: number | null
  month: string
  onClose: () => void
  onShowStudent?: (studentId: number) => void
}

export function ClassProfile({ classId, month, onClose, onShowStudent }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useAlert()
  // A class can hold thirty students; the dialog cannot.
  const studentsPage = usePagination(profile?.students ?? [], 15)

  useEffect(() => {
    setError(null)
    if (classId === null) {
      setProfile(null)
      return
    }
    apiGet<Profile>(`/api/classes/${classId}/profile?month=${month}`)
      .then(setProfile)
      .catch((err: Error) => setError(err.message))
  }, [classId, month, setError])

  return (
    <Dialog open={classId !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{profile?.subject_name ?? "Classe"}</DialogTitle>
        </DialogHeader>
        <Notice alert={error} />
        {profile && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              {profile.is_active ? (
                <Badge className="bg-success/15 text-success border-success/20 border">
                  Active
                </Badge>
              ) : (
                <Badge variant="outline">Archivée</Badge>
              )}
              {profile.teacher_id === null && (
                <Badge variant="destructive">Sans professeur</Badge>
              )}
            </div>

            <FieldGrid>
              <Field label="Créneau">{segmentLabel(profile)}</Field>
              <Field label="Professeur">
                {profile.teacher_name ?? "— à pourvoir"}
              </Field>
              <Field label={`Inscrits — ${monthLabel(month)}`}>
                {profile.enrolled_count}
              </Field>
            </FieldGrid>

            <div>
              <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                Qui l'a enseignée
              </p>
              <div className="space-y-1">
                {profile.assignments.map((period, index) => (
                  <p key={index} className="text-sm">
                    <span className="font-medium">{period.teacher_name}</span>
                    <span className="text-muted-foreground">
                      {" "}
                      —{" "}
                      {period.from_date
                        ? `du ${period.from_date}`
                        : "depuis le début"}
                      {period.to_date ? ` au ${period.to_date}` : " (en cours)"}
                    </span>
                  </p>
                ))}
                {profile.assignments.length === 0 && (
                  <p className="text-muted-foreground text-sm">
                    Personne pour l'instant.
                  </p>
                )}
              </div>
            </div>

            {/* How much goes to the salle, to the academie, to the
                teacher -- and where that figure comes from. */}
            <ClassSplit classId={profile.id} />

            <ShareSection classId={profile.id} month={month} />

            <div>
              <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                Élèves inscrits
              </p>
              {profile.students.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  Aucun élève ce mois-ci.
                </p>
              )}
              {profile.students.length > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Élève</TableHead>
                      <TableHead>État du mois</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {studentsPage.visible.map((student) => (
                      <TableRow
                        key={student.student_id}
                        className={onShowStudent ? "cursor-pointer" : ""}
                        title={onShowStudent ? "Ouvrir le profil" : undefined}
                        onClick={(event) => {
                          if (!onShowStudent) return
                          const target = event.target as HTMLElement
                          if (!event.currentTarget.contains(target)) return
                          onShowStudent(student.student_id)
                        }}
                      >
                        <TableCell className="font-medium">
                          {[student.first_name, student.student_name]
                            .filter(Boolean)
                            .join(" ")}
                        </TableCell>
                        <TableCell>
                          {student.paid ? (
                            <Badge className="bg-success/15 text-success border-success/20 border">
                              Payé
                            </Badge>
                          ) : (
                            <Badge variant="destructive">Impayé</Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              <Pagination
                {...studentsPage}
                shown={studentsPage.visible.length}
                noun="élèves"
              />
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Who gets what on this class, this month.

    By default the app splits by the number of days taught -- fair, and
    automatic. But the owner decides: a teacher who left mid-month may have
    prepared everything, a stand-in may have done double duty. He then sets
    the shares in percentages (a fixed amount would become wrong the moment
    a student enrolls or a reduction lands). */
function ShareSection({ classId, month }: { classId: number; month: string }) {
  const [share, setShare] = useState<ClassShare | null>(null)
  const [draft, setDraft] = useState<Record<number, string> | null>(null)
  const [note, setNote] = useAlert()
  const [busy, setBusy] = useState(false)

  const reload = useCallback(() => {
    apiGet<ClassShare>(`/api/classes/${classId}/share?month=${month}`)
      .then(setShare)
      .catch((err: Error) => setNote(err.message))
  }, [classId, month, setNote])
  useEffect(reload, [reload])

  if (!share || share.shares.length === 0) return null
  // A single teacher across the whole month: nothing to split.
  if (share.shares.length === 1 && !share.manual) return null

  const total = draft
    ? Object.values(draft).reduce((sum, value) => sum + (Number(value) || 0), 0)
    : 100

  const save = () => {
    if (!draft) return
    setBusy(true)
    setNote(null)
    apiSend("PUT", `/api/classes/${classId}/share`, {
      month,
      shares: Object.entries(draft).map(([teacherId, percent]) => ({
        teacher_id: Number(teacherId),
        share_bp: Math.round((Number(percent) || 0) * 100),
      })),
    })
      .then(() => {
        setDraft(null)
        reload()
      })
      .catch((err: Error) => setNote(err.message))
      .finally(() => setBusy(false))
  }

  const backToAutomatic = () => {
    setBusy(true)
    apiSend("DELETE", `/api/classes/${classId}/share?month=${month}`)
      .then(() => {
        setDraft(null)
        reload()
      })
      .catch((err: Error) => setNote(err.message))
      .finally(() => setBusy(false))
  }

  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Répartition entre professeurs — {monthLabel(month)}
        </p>
        {share.manual ? (
          <Badge variant="outline">fixée à la main</Badge>
        ) : (
          <Badge variant="outline">selon les jours</Badge>
        )}
      </div>

      <div className="border-border divide-border divide-y rounded-xl border">
        {share.shares.map((row) => (
          <div
            key={row.teacher_id}
            className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
          >
            <span className="min-w-0">
              <span className="font-medium">{row.teacher_name}</span>
              <span className="text-muted-foreground text-xs">
                {" "}
                · {row.days} jour(s) enseigné(s)
              </span>
            </span>
            {draft ? (
              <span className="flex items-center gap-1">
                <Input
                  value={draft[row.teacher_id] ?? "0"}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      [row.teacher_id]: event.target.value,
                    }))
                  }
                  className="h-8 w-16 text-right"
                  inputMode="decimal"
                />
                <span className="text-muted-foreground text-xs">%</span>
              </span>
            ) : (
              <span className="font-medium">{row.share_bp / 100}%</span>
            )}
          </div>
        ))}
      </div>

      {draft && total !== 100 && (
        <p className="text-destructive mt-1.5 text-xs">
          Le total fait {total}% — il doit faire exactement 100%.
        </p>
      )}
      <Notice alert={note} />

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {draft ? (
          <>
            <Button size="sm" onClick={save} disabled={busy || total !== 100}>
              {busy ? "…" : "Enregistrer"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
              Annuler
            </Button>
          </>
        ) : (
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                setDraft(
                  Object.fromEntries(
                    share.shares.map((row) => [
                      row.teacher_id,
                      String(row.share_bp / 100),
                    ]),
                  ),
                )
              }
            >
              Ajuster les parts
            </Button>
            {share.manual && (
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={backToAutomatic}
              >
                Revenir au partage par jours
              </Button>
            )}
          </>
        )}
        <span className="text-muted-foreground text-xs">
          s'applique aux encaissements à venir de ce mois — ce qui est déjà
          encaissé ne bouge pas
        </span>
      </div>
    </div>
  )
}
