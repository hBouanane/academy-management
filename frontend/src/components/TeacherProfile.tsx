// One professor, whole story: classes with student counts and what each one
// actually paid him, capabilities, six-month history, assignment periods.

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
import { monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import type { TeacherProfile as Profile } from "@/lib/api"
import { segmentLabel } from "@/lib/levels"
import { formatDH } from "@/lib/money"

type Props = {
  teacherId: number | null
  month: string
  onClose: () => void
  onChanged?: () => void
}

export function TeacherProfile({ teacherId, month, onClose, onChanged }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    setError(null)
    if (teacherId === null) {
      setProfile(null)
      return
    }
    apiGet<Profile>(`/api/teachers/${teacherId}/profile?month=${month}`)
      .then(setProfile)
      .catch((err: Error) => setError(err.message))
  }, [teacherId, month, refresh])

  // A checked leaf becomes a real class in one click — no wizard.
  const openClass = (capability: Profile["capabilities"][number]) => {
    apiSend("POST", "/api/classes", {
      level_id: capability.level_id,
      subject_id: capability.subject_id,
      teacher_id: teacherId,
      annee: capability.annee,
      parcours: capability.parcours,
    })
      .then(() => {
        setRefresh((count) => count + 1)
        onChanged?.()
      })
      .catch((err: Error) => setError(err.message))
  }

  const alreadyTeaches = (capability: Profile["capabilities"][number]) =>
    (profile?.classes ?? []).some(
      (row) =>
        row.is_active === 1 &&
        row.teacher_id === teacherId &&
        row.subject_id === capability.subject_id &&
        row.level_id === capability.level_id &&
        row.annee === capability.annee &&
        row.parcours === capability.parcours,
    )

  const monthTotal =
    profile?.history.find((entry) => entry.month === month)?.earned ?? 0

  return (
    <Dialog open={teacherId !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{profile?.name ?? "Profil professeur"}</DialogTitle>
        </DialogHeader>
        <Notice message={error} />
        {profile && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              {profile.is_owner ? (
                <Badge variant="outline">Propriétaire</Badge>
              ) : null}
              {profile.phone && <Badge variant="outline">{profile.phone}</Badge>}
              <Badge variant="outline">
                Depuis le {profile.created_at?.slice(0, 10) ?? "—"}
              </Badge>
              <Badge className="bg-success/15 text-success border-success/20 border">
                {formatDH(monthTotal)} — {monthLabel(month)}
              </Badge>
            </div>

            <div>
              <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                Classes
              </p>
              {profile.classes.length === 0 && (
                <p className="text-muted-foreground text-sm">Aucune classe.</p>
              )}
              {profile.classes.length > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Classe</TableHead>
                      <TableHead>Segment</TableHead>
                      <TableHead>Inscrits</TableHead>
                      <TableHead className="text-right">
                        Gagné ({monthLabel(month)})
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {profile.classes.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell className="font-medium">
                          {row.subject_name}
                          {row.teacher_id !== profile.id && (
                            <span className="text-muted-foreground text-xs">
                              {" "}
                              (ancien)
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {segmentLabel(row)}
                        </TableCell>
                        <TableCell>{row.enrolled_count}</TableCell>
                        <TableCell className="text-right font-medium">
                          {formatDH(row.earned_centimes)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                  6 derniers mois
                </p>
                <div className="space-y-1">
                  {profile.history.map((entry) => (
                    <div
                      key={entry.month}
                      className="flex items-center justify-between text-sm"
                    >
                      <span className="text-muted-foreground capitalize">
                        {monthLabel(entry.month)}
                      </span>
                      <span className={entry.earned > 0 ? "font-medium" : "text-muted-foreground"}>
                        {formatDH(entry.earned)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                  Compétences
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {profile.capabilities.map((capability) => (
                    <span
                      key={capability.id}
                      className="bg-secondary text-secondary-foreground flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs"
                    >
                      {capability.subject_name} · {capability.level_name}
                      {capability.annee ? ` ${capability.annee}` : ""}
                      {capability.parcours ? ` ${capability.parcours}` : ""}
                      {!alreadyTeaches(capability) && (
                        <button
                          className="text-primary font-medium underline-offset-2 hover:underline"
                          title="Créer la classe correspondante, enseignée par lui"
                          onClick={() => openClass(capability)}
                        >
                          ouvrir la classe
                        </button>
                      )}
                    </span>
                  ))}
                  {profile.capabilities.length === 0 && (
                    <p className="text-muted-foreground text-sm">
                      Aucune — modifiez le professeur pour cocher son arbre.
                    </p>
                  )}
                </div>
              </div>
            </div>

            {profile.assignments.length > 0 && (
              <div>
                <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                  Périodes d'enseignement
                </p>
                <div className="space-y-1">
                  {profile.assignments.map((assignment, index) => (
                    <p key={index} className="text-muted-foreground text-sm">
                      {assignment.subject_name} · Groupe {assignment.group_name} (
                      {assignment.level_name}) —{" "}
                      {assignment.from_date
                        ? `du ${assignment.from_date}`
                        : "depuis le début"}
                      {assignment.to_date ? ` au ${assignment.to_date}` : " (en cours)"}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
