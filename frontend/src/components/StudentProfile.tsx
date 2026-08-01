// One student, whole story: identity, tagged phones, and every month —
// pack, matières, net, paid state. Archived students keep their history.

import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { PayDialog } from "@/components/PayDialog"
import { apiGet } from "@/lib/api"
import type { StudentProfile as Profile } from "@/lib/api"
import { anneeLabel } from "@/lib/levels"
import { formatDH } from "@/lib/money"

type Props = {
  studentId: number | null
  onClose: () => void
  /** Called after a payment made from the profile — refresh the page behind. */
  onChanged?: () => void
}

export function StudentProfile({ studentId, onClose, onChanged }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Any unpaid month is payable right here, no month navigation needed.
  const [payId, setPayId] = useState<number | null>(null)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    setError(null)
    if (studentId === null) {
      setProfile(null)
      return
    }
    apiGet<Profile>(`/api/students/${studentId}/profile`)
      .then(setProfile)
      .catch((err: Error) => setError(err.message))
  }, [studentId, refresh])

  const fullName = profile
    ? [profile.first_name, profile.name].filter(Boolean).join(" ")
    : ""
  const annee = profile ? anneeLabel(profile.level_name, profile.annee) : null

  return (
    <Dialog open={studentId !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{fullName || "Profil étudiant"}</DialogTitle>
        </DialogHeader>
        <Notice message={error} />
        {profile && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">
                {profile.level_name}
                {annee ? ` · ${annee}` : ""}
              </Badge>
              {profile.filiere && <Badge variant="outline">{profile.filiere}</Badge>}
              {profile.school_name && (
                <Badge variant="outline">{profile.school_name}</Badge>
              )}
              {profile.months.length === 0 && (
                <Badge className="bg-secondary text-secondary-foreground">
                  Pré-inscrit
                </Badge>
              )}
              {!profile.is_active && <Badge variant="outline">Archivé</Badge>}
            </div>

            <div>
              <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                Téléphones
              </p>
              {profile.phones.length === 0 && (
                <p className="text-muted-foreground text-sm">Aucun numéro.</p>
              )}
              <div className="flex flex-wrap gap-1.5">
                {profile.phones.map((phone, index) => (
                  <span
                    key={index}
                    className="bg-secondary text-secondary-foreground rounded-full px-2.5 py-0.5 text-xs"
                  >
                    {phone.tag} · {phone.number}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                Historique des mois
              </p>
              {profile.months.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  Jamais inscrit — utilisez « Inscrire » pour commencer.
                </p>
              )}
              {profile.months.length > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Mois</TableHead>
                      <TableHead>Forfait</TableHead>
                      <TableHead>Matières</TableHead>
                      <TableHead className="text-right">Net</TableHead>
                      <TableHead>Statut</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {profile.months.map((month) => (
                      <TableRow
                        key={month.enrollment_id}
                        className={month.paid ? "" : "row-unpaid"}
                      >
                        <TableCell className="capitalize">
                          {monthLabel(month.month)}
                          {month.arrival_date && (
                            <p className="text-muted-foreground text-xs">
                              début le {month.arrival_date.slice(8, 10)}
                            </p>
                          )}
                        </TableCell>
                        <TableCell>{month.subject_count} matière(s)</TableCell>
                        <TableCell className="text-muted-foreground">
                          {month.subjects.join(", ") || "—"}
                        </TableCell>
                        <TableCell className="text-right font-medium">
                          {formatDH(month.net_centimes)}
                        </TableCell>
                        <TableCell>
                          {month.paid ? (
                            <Badge className="bg-success/15 text-success border-success/20 border">
                              Payé{month.paid_on ? ` · ${month.paid_on}` : ""}
                            </Badge>
                          ) : (
                            <span className="flex items-center gap-2">
                              <Badge variant="destructive">Impayé</Badge>
                              <Button
                                size="sm"
                                onClick={() => setPayId(month.enrollment_id)}
                              >
                                Encaisser
                              </Button>
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>

            <p className="text-muted-foreground text-xs">
              Fiche créée le {profile.created_at?.slice(0, 10) ?? "—"}
            </p>
          </div>
        )}
      </DialogContent>

      {payId !== null && (
        <PayDialog
          enrollmentId={payId}
          studentName={fullName}
          open
          onOpenChange={(next) => {
            if (!next) setPayId(null)
          }}
          onDone={() => {
            setPayId(null)
            setRefresh((count) => count + 1)
            onChanged?.()
          }}
        />
      )}
    </Dialog>
  )
}
