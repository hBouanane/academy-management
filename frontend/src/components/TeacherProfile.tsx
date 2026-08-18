// One professor, whole story: classes with student counts and what each one
// actually paid him, capabilities, six-month history, assignment periods.

import { useEffect, useState } from "react"
import { FileText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
import { apiGet, apiSend } from "@/lib/api"
import type { TeacherProfile as Profile } from "@/lib/api"
import { segmentLabel } from "@/lib/levels"
import { formatDH } from "@/lib/money"

const capabilityLabel = (capability: Profile["capabilities"][number]) =>
  `${capability.subject_name} · ${capability.level_name}${
    capability.annee ? ` ${capability.annee}` : ""
  }${capability.parcours ? ` ${capability.parcours}` : ""}`

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
  // Batch class creation: check several capabilities, one « Créer » click.
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)

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

  const openable = (profile?.capabilities ?? []).filter(
    (capability) => !alreadyTeaches(capability),
  )

  const createSelected = async () => {
    setBusy(true)
    for (const capability of openable.filter((c) => selected.has(c.id))) {
      await apiSend("POST", "/api/classes", {
        level_id: capability.level_id,
        subject_id: capability.subject_id,
        teacher_id: teacherId,
        annee: capability.annee,
        parcours: capability.parcours,
      }).catch((err: Error) => setError(err.message))
    }
    setSelected(new Set())
    setBusy(false)
    setRefresh((count) => count + 1)
    onChanged?.()
  }

  const monthTotal =
    profile?.history.find((entry) => entry.month === month)?.earned ?? 0

  return (
    <Dialog open={teacherId !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-3">
            {profile?.name ?? "Profil professeur"}
            {profile && (
              <Button size="sm" variant="outline" asChild>
                <a
                  href={`/api/teachers/${profile.id}/invoice.docx?month=${month}`}
                  download
                  title="Sa fiche de paie du mois, à imprimer et signer"
                >
                  <FileText className="size-4" /> Fiche de paie
                </a>
              </Button>
            )}
          </DialogTitle>
        </DialogHeader>
        <Notice message={error} />
        {profile && (
          <div className="space-y-5">
            <FieldGrid>
              <Field label="Rôle">
                {profile.is_owner ? "Propriétaire + professeur" : "Professeur"}
              </Field>
              <Field label="Téléphone">{profile.phone ?? "—"}</Field>
              <Field label="Depuis le">
                {profile.created_at?.slice(0, 10) ?? "—"}
              </Field>
              <Field
                label={`Gagné comme professeur — ${monthLabel(month)}`}
              >
                <span className={monthTotal > 0 ? "text-success" : ""}>
                  {formatDH(monthTotal)}
                </span>
              </Field>
              {profile.is_owner === 1 && (
                <Field label="Gagné comme propriétaire">
                  <span className={profile.owner_earned > 0 ? "text-success" : ""}>
                    {formatDH(profile.owner_earned)}
                  </span>
                </Field>
              )}
              {profile.is_owner === 1 && (
                <Field label="Total du mois">
                  <span className="text-success font-semibold">
                    {formatDH(monthTotal + profile.owner_earned)}
                  </span>
                </Field>
              )}
            </FieldGrid>

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
                <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                  Compétences
                </p>
                <p className="text-muted-foreground mb-1.5 text-xs">
                  Ce qu'il peut enseigner — cochez pour ouvrir les classes qui
                  manquent
                </p>
                {/* Deux états lisibles sans pictogramme : la classe ouverte
                    est une pastille pleine et calme, celle qui manque garde
                    sa case à cocher. */}
                {openable.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {openable.map((capability) => (
                      <label
                        key={capability.id}
                        className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                          selected.has(capability.id)
                            ? "border-primary text-foreground"
                            : "border-border border-dashed"
                        }`}
                      >
                        <Checkbox
                          checked={selected.has(capability.id)}
                          onCheckedChange={(state) =>
                            setSelected((current) => {
                              const next = new Set(current)
                              if (state === true) next.add(capability.id)
                              else next.delete(capability.id)
                              return next
                            })
                          }
                        />
                        {capabilityLabel(capability)}
                      </label>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap gap-1.5">
                  {profile.capabilities.filter(alreadyTeaches).map((capability) => (
                    <span
                      key={capability.id}
                      className="bg-secondary text-secondary-foreground rounded-full px-2.5 py-0.5 text-xs"
                      title="Classe déjà ouverte"
                    >
                      {capabilityLabel(capability)}
                    </span>
                  ))}
                  {profile.capabilities.length === 0 && (
                    <p className="text-muted-foreground text-sm">
                      Aucune — modifiez le professeur pour cocher son arbre.
                    </p>
                  )}
                </div>
                {openable.length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <label className="text-muted-foreground flex items-center gap-1.5 text-xs">
                      <Checkbox
                        checked={openable.every((c) => selected.has(c.id))}
                        onCheckedChange={(state) =>
                          setSelected(
                            state === true
                              ? new Set(openable.map((c) => c.id))
                              : new Set(),
                          )
                        }
                      />
                      Tout sélectionner
                    </label>
                    <Button
                      size="sm"
                      disabled={selected.size === 0 || busy}
                      onClick={createSelected}
                    >
                      {busy ? "…" : `Créer les classes (${selected.size})`}
                    </Button>
                  </div>
                )}
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
                      {assignment.subject_name} · {assignment.level_name} —{" "}
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
