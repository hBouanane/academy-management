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
import { CompleteDialog } from "@/components/CompleteDialog"
import { Field, FieldGrid } from "@/components/Field"
import { Pagination, usePagination } from "@/components/Pagination"
import { MessageCircle } from "lucide-react"
import { monthLabel } from "@/components/MonthNav"
import { WhatsAppDialog } from "@/components/WhatsAppDialog"
import { Notice } from "@/components/Notice"
import { PayDialog } from "@/components/PayDialog"
import { apiGet } from "@/lib/api"
import type { StudentProfile as Profile } from "@/lib/api"
import { anneeLabel } from "@/lib/levels"
import { currentMonth, formatDH } from "@/lib/money"
import { useAlert } from "@/lib/alert"

type Props = {
  studentId: number | null
  onClose: () => void
  /** Called after a payment made from the profile — refresh the page behind. */
  onChanged?: () => void
}

export function StudentProfile({ studentId, onClose, onChanged }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useAlert()
  // Any unpaid month is payable right here, no month navigation needed.
  const [payId, setPayId] = useState<number | null>(null)
  // Completing an avance, likewise.
  const [completeTarget, setCompleteTarget] = useState<{
    paymentId: number
    remaining: number
  } | null>(null)
  const [refresh, setRefresh] = useState(0)
  // Twelve rows a year, for as long as the student stays.
  const monthsPage = usePagination(profile?.months ?? [], 12)

  useEffect(() => {
    setError(null)
    if (studentId === null) {
      setProfile(null)
      return
    }
    apiGet<Profile>(`/api/students/${studentId}/profile`)
      .then(setProfile)
      .catch((err: Error) => setError(err.message))
  }, [studentId, refresh, setError])
  const [writing, setWriting] = useState(false)

  const fullName = profile
    ? [profile.first_name, profile.name].filter(Boolean).join(" ")
    : ""
  const annee = profile ? anneeLabel(profile.level_name, profile.annee) : null

  return (
    <>
    <Dialog open={studentId !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-3">
            {fullName || "Profil étudiant"}
            {/* Writing to the family from the record: this is where his
                history is read, so this is where one decides to call. */}
            {studentId !== null && (
              <Button
                size="sm"
                variant="outline"
                className="text-success hover:text-success border-success/40"
                onClick={() => setWriting(true)}
                title="Prévenir la famille par WhatsApp"
              >
                <MessageCircle className="size-4" />
                WhatsApp
              </Button>
            )}
          </DialogTitle>
        </DialogHeader>
        <Notice alert={error} />
        {profile && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              {profile.months.length === 0 ? (
                <Badge className="bg-secondary text-secondary-foreground">
                  Pré-inscrit
                </Badge>
              ) : profile.is_active ? (
                <Badge className="bg-success/15 text-success border-success/20 border">
                  Actif
                </Badge>
              ) : (
                <Badge variant="outline">Archivé</Badge>
              )}
            </div>

            <FieldGrid>
              <Field label="Niveau">
                {profile.level_name}
                {annee ? ` — ${annee}` : ""}
              </Field>
              {profile.parcours && (
                <Field label="Parcours">{profile.parcours}</Field>
              )}
              {profile.filiere && <Field label="Filière">{profile.filiere}</Field>}
              <Field label="École">{profile.school_name ?? "—"}</Field>
              <Field label="Fiche créée le">
                {profile.created_at?.slice(0, 10) ?? "—"}
              </Field>
              <Field
                label={
                  profile.phones.length > 1 ? "Téléphones" : "Téléphone"
                }
              >
                {profile.phones.length === 0 && "—"}
                {profile.phones.map((phone, index) => (
                  <p key={index}>
                    {phone.number}{" "}
                    <span className="text-muted-foreground text-xs font-normal">
                      ({phone.tag})
                    </span>
                  </p>
                ))}
              </Field>
            </FieldGrid>

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
                    {monthsPage.visible.map((month) => (
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
                          {month.paid && month.remaining_centimes > 0 ? (
                            <span className="flex items-center gap-2">
                              <Badge className="border-amber-500/25 bg-amber-500/15 text-amber-600 border">
                                Avance · reste {formatDH(month.remaining_centimes)}
                              </Badge>
                              {month.payment_id && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() =>
                                    setCompleteTarget({
                                      paymentId: month.payment_id!,
                                      remaining: month.remaining_centimes,
                                    })
                                  }
                                >
                                  Compléter
                                </Button>
                              )}
                            </span>
                          ) : month.paid ? (
                            <span className="flex flex-wrap items-center gap-1">
                              <Badge className="bg-success/15 text-success border-success/20 border">
                                Payé{month.paid_on ? ` · ${month.paid_on}` : ""}
                              </Badge>
                              {month.refund_pending_centimes > 0 && (
                                <Badge
                                  variant="destructive"
                                  title="Classe archivée — à lui rendre"
                                >
                                  à rembourser{" "}
                                  {formatDH(month.refund_pending_centimes)}
                                </Badge>
                              )}
                              {month.refunded_centimes > 0 && (
                                <Badge variant="outline" title="Argent déjà rendu">
                                  remboursé {formatDH(month.refunded_centimes)}
                                </Badge>
                              )}
                            </span>
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
              <Pagination
                {...monthsPage}
                shown={monthsPage.visible.length}
                noun="mois"
              />
            </div>

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

      {completeTarget && (
        <CompleteDialog
          paymentId={completeTarget.paymentId}
          studentName={fullName}
          remainingCentimes={completeTarget.remaining}
          onClose={() => setCompleteTarget(null)}
          onDone={() => {
            setCompleteTarget(null)
            setRefresh((count) => count + 1)
            onChanged?.()
          }}
        />
      )}
    </Dialog>
      {writing && studentId !== null && (
        <WhatsAppDialog
          studentId={studentId}
          studentName={fullName}
          month={currentMonth()}
          onClose={() => setWriting(false)}
        />
      )}
    </>
  )
}
