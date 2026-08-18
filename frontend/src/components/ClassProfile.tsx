// Une classe, toute son histoire : son créneau, qui l'enseigne aujourd'hui,
// qui l'a enseignée et depuis quand (les reprises se lisent d'un coup
// d'œil), et les élèves inscrits ce mois-ci avec leur état de paiement.

import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
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
import { Notice } from "@/components/Notice"
import { apiGet } from "@/lib/api"
import type { ClassProfile as Profile } from "@/lib/api"
import { segmentLabel } from "@/lib/levels"

type Props = {
  classId: number | null
  month: string
  onClose: () => void
  onShowStudent?: (studentId: number) => void
}

export function ClassProfile({ classId, month, onClose, onShowStudent }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    if (classId === null) {
      setProfile(null)
      return
    }
    apiGet<Profile>(`/api/classes/${classId}/profile?month=${month}`)
      .then(setProfile)
      .catch((err: Error) => setError(err.message))
  }, [classId, month])

  return (
    <Dialog open={classId !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{profile?.subject_name ?? "Classe"}</DialogTitle>
        </DialogHeader>
        <Notice message={error} />
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
                    {profile.students.map((student) => (
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
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
