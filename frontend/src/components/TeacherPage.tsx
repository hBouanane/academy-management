// One professor, one page: what he earned this month, where it came from,
// what he could teach, and when he taught it.
//
// Everything the page holds is visible on arrival. The previous version hid
// eleven dormant classes and ten open capabilities behind « Afficher … »
// toggles, which meant the page lied about its own size: "12 classes" was
// really "1 class and a button". A long list is sorted so the important rows
// come first, and muted so the eye skips the rest -- it is never removed.
//
// Every collection is a table with headers. Pills read as decoration and
// force the reader to infer the columns; a header states them. That matters
// most for the capabilities, where « Oui / Non » in a column answers a
// question that a filled-versus-dashed pill only hinted at.

import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, Pencil, UserMinus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ArchiveTeacherDialog } from "@/components/ArchiveTeacherDialog"
import { FileDocument } from "@/components/FileDocument"
import { MonthNav, monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { Pagination, usePagination } from "@/components/Pagination"
import { TeacherDialog } from "@/components/TeacherDialog"
import { apiGet, apiSend } from "@/lib/api"
import type { Capability, Teacher, TeacherProfile as Profile } from "@/lib/api"
import { segmentLabel } from "@/lib/levels"
import { formatDH } from "@/lib/money"
import { useAlert } from "@/lib/alert"

/** A capability names a teachable slot, not a class: level, year, and the
    3ème-collège fork. The class may or may not exist yet. */
const capabilityLevel = (capability: Capability) =>
  segmentLabel({
    level_name: capability.level_name,
    annee: capability.annee,
    parcours: capability.parcours,
    filiere: null,
  })

/** Every case gets its own phrasing. A single template produced « depuis le
    début au 2026-08-01 », which is not a sentence anyone would write. */
function periodWording(from: string | null, to: string | null): string {
  if (from && to) return `du ${from} au ${to}`
  if (from) return `depuis le ${from}`
  if (to) return `jusqu'au ${to}`
  return "depuis le début"
}

type Props = {
  teacherId: number
  month: string
  setMonth: (month: string) => void
  onClose: () => void
  onChanged?: () => void
}

export function TeacherPage({
  teacherId,
  month,
  setMonth,
  onClose,
  onChanged,
}: Props) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useAlert()
  const [refresh, setRefresh] = useState(0)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [departing, setDeparting] = useState(false)
  // Archiving asks who takes over, so it needs the other teachers.
  const [colleagues, setColleagues] = useState<Teacher[]>([])

  useEffect(() => {
    setError(null)
    setLoading(true)
    apiGet<Profile>(`/api/teachers/${teacherId}/profile?month=${month}`)
      .then(setProfile)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [teacherId, month, refresh, setError])

  useEffect(() => {
    apiGet<Teacher[]>("/api/teachers")
      .then(setColleagues)
      .catch(() => setColleagues([]))
  }, [refresh])

  const alreadyTeaches = (capability: Capability) =>
    (profile?.classes ?? []).some(
      (row) =>
        row.is_active === 1 &&
        row.teacher_id === teacherId &&
        row.subject_id === capability.subject_id &&
        row.level_id === capability.level_id &&
        row.annee === capability.annee &&
        row.parcours === capability.parcours,
    )

  // Not-yet-open first: those are the only rows he can act on, and a
  // checkbox column that starts with ten disabled boxes looks broken.
  const capabilities = useMemo(() => {
    const rows = (profile?.capabilities ?? []).map((capability) => ({
      capability,
      open: alreadyTeaches(capability),
    }))
    return rows.sort(
      (a, b) =>
        Number(a.open) - Number(b.open) ||
        a.capability.subject_name.localeCompare(b.capability.subject_name),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile, teacherId])

  const openable = capabilities.filter((row) => !row.open)

  const createSelected = async () => {
    setBusy(true)
    for (const { capability } of openable) {
      if (!selected.has(capability.id)) continue
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

  // Sorted, never filtered: what earns leads, then what has students, then
  // the rest. The zero rows stay on the page because he opened it to see
  // his classes -- all of them.
  const classes = useMemo(
    () =>
      [...(profile?.classes ?? [])].sort(
        (a, b) =>
          b.earned_centimes - a.earned_centimes ||
          b.enrolled_count - a.enrolled_count ||
          a.subject_name.localeCompare(b.subject_name),
      ),
    [profile],
  )

  const withStudents = classes.filter((row) => row.enrolled_count > 0).length
  const classesSum = classes.reduce((sum, row) => sum + row.earned_centimes, 0)
  const enrolledSum = classes.reduce((sum, row) => sum + row.enrolled_count, 0)
  // An advance paid on an enrollment passes through no payment, so no class
  // can claim it. The gap is real; leaving it unexplained makes both figures
  // look wrong.
  const unattached = monthTotal - classesSum

  // Identical periods are counted, not repeated: thirteen consecutive
  // « francais · Collège — depuis le début » lines cannot be read.
  const periods = useMemo(() => {
    const grouped = new Map<
      string,
      {
        subject: string
        level: string
        wording: string
        ended: boolean
        count: number
      }
    >()
    for (const item of profile?.assignments ?? []) {
      const wording = periodWording(item.from_date, item.to_date)
      const key = `${item.subject_name}|${item.level_name}|${wording}`
      const seen = grouped.get(key)
      if (seen) {
        seen.count += 1
        continue
      }
      grouped.set(key, {
        subject: item.subject_name,
        level: item.level_name,
        wording,
        ended: Boolean(item.to_date),
        count: 1,
      })
    }
    return [...grouped.values()].sort(
      (a, b) =>
        Number(a.ended) - Number(b.ended) || a.subject.localeCompare(b.subject),
    )
  }, [profile])

  // Totals below are computed on the full lists, never on the visible page:
  // a total that counted one page would simply be wrong.
  const classesPage = usePagination(classes, 25)
  const capabilitiesPage = usePagination(capabilities, 25)

  const peak = Math.max(...(profile?.history ?? []).map((e) => e.earned), 1)
  const isOwner = profile?.is_owner === 1
  const nothingAtAll =
    profile !== null &&
    profile.classes.length === 0 &&
    profile.capabilities.length === 0 &&
    profile.assignments.length === 0

  return (
    <div className="view-enter space-y-8">
      <header className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <Button size="sm" variant="ghost" onClick={onClose}>
              <ArrowLeft className="size-4" />
              Retour
            </Button>
            <div>
              <h2 className="text-2xl font-medium tracking-tight">
                {profile?.name ?? "Professeur"}
              </h2>
              <p className="text-muted-foreground text-sm">
                {isOwner ? "Propriétaire + professeur" : "Professeur"}
              </p>
            </div>
          </div>

          {/* The month belongs in the header because every figure below is
              scoped to it. Reading « Gagné » without seeing which month is
              how a number gets trusted for the wrong period. */}
          <div className="flex flex-wrap items-center gap-2">
            <MonthNav month={month} setMonth={setMonth} />
            <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
              <Pencil className="size-4" />
              Modifier
            </Button>
            <FileDocument
              kind="payslip"
              month={month}
              refId={teacherId}
              size="sm"
              variant="outline"
              downloadHref={`/api/teachers/${teacherId}/invoice.docx?month=${month}`}
            >
              Facture
            </FileDocument>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setDeparting(true)}
              disabled={profile === null}
            >
              <UserMinus className="size-4" />
              Archiver
            </Button>
          </div>
        </div>

        {/* Reference data, not results: it answers "who is this", never
            "how much". Kept small so it never competes with the money. */}
        <p className="text-muted-foreground text-xs">
          {profile?.phone ?? "Pas de téléphone"}
          {" · depuis le "}
          {profile?.created_at?.slice(0, 10) ?? "—"}
        </p>
      </header>

      <Notice alert={error} />

      {loading && (
        <p className="text-muted-foreground text-sm">Chargement du profil…</p>
      )}

      {!loading && profile && (
        <div className="space-y-8">
          {/* One decomposition, read downwards as a sum. Three side-by-side
              cells made the reader add 60,00 and 73,54 himself before he
              could trust the 133,54 sitting next to them. */}
          <section className="max-w-xl">
            <h3 className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
              Ce qu'il gagne en {monthLabel(month).toLowerCase()}
            </h3>
            <Table>
              <TableBody>
                <TableRow>
                  <TableCell>Comme professeur</TableCell>
                  <TableCell className="text-right">
                    {formatDH(monthTotal)}
                  </TableCell>
                </TableRow>
                {isOwner && (
                  <TableRow>
                    <TableCell>Comme propriétaire</TableCell>
                    <TableCell className="text-right">
                      {formatDH(profile.owner_earned)}
                    </TableCell>
                  </TableRow>
                )}
                {isOwner && (
                  <TableRow>
                    <TableCell className="font-medium">
                      Total du mois
                    </TableCell>
                    <TableCell className="text-success text-right font-semibold">
                      {formatDH(monthTotal + profile.owner_earned)}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </section>

          {nothingAtAll && (
            <p className="text-muted-foreground text-sm">
              Ce professeur n'a encore ni classe, ni compétence déclarée, ni
              période d'enseignement. Modifiez sa fiche pour cocher ce qu'il
              peut enseigner.
            </p>
          )}

          {classes.length > 0 && (
            <section>
              <h3 className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                Classes — {classes.length}, dont {withStudents} avec inscrit en{" "}
                {monthLabel(month).toLowerCase()}
              </h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Classe</TableHead>
                    <TableHead>Segment</TableHead>
                    <TableHead className="text-right">Inscrits</TableHead>
                    <TableHead className="text-right">
                      Gagné ({monthLabel(month).toLowerCase()})
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {classesPage.visible.map((row) => {
                    const quiet =
                      row.enrolled_count === 0 && row.earned_centimes === 0
                    return (
                      <TableRow
                        key={row.id}
                        className={quiet ? "text-muted-foreground" : ""}
                      >
                        <TableCell className={quiet ? "" : "font-medium"}>
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
                        <TableCell className="text-right">
                          {row.enrolled_count}
                        </TableCell>
                        <TableCell
                          className={
                            quiet ? "text-right" : "text-right font-medium"
                          }
                        >
                          {formatDH(row.earned_centimes)}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  <TableRow>
                    <TableCell colSpan={2} className="font-medium">
                      Total des classes
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {enrolledSum}
                    </TableCell>
                    <TableCell className="text-right font-semibold">
                      {formatDH(classesSum)}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
              <Pagination
                {...classesPage}
                shown={classesPage.visible.length}
                noun="classes"
              />
              {unattached !== 0 && (
                <p className="text-muted-foreground mt-1.5 text-xs">
                  {formatDH(Math.abs(unattached))}{" "}
                  {unattached > 0 ? "de plus" : "de moins"} sur son total du
                  mois — une avance versée sur une inscription ne passe par
                  aucune classe.
                </p>
              )}
            </section>
          )}

          {profile.history.length > 0 && (
            <section className="max-w-xl">
              <h3 className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                Historique — 6 derniers mois
              </h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Mois</TableHead>
                    <TableHead className="text-right">Gagné</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {profile.history.map((entry) => (
                    <TableRow
                      key={entry.month}
                      className={entry.month === month ? "bg-muted/50" : ""}
                    >
                      <TableCell className="capitalize">
                        {monthLabel(entry.month)}
                        {entry.month === month && (
                          <span className="text-muted-foreground text-xs">
                            {" "}
                            · affiché
                          </span>
                        )}
                      </TableCell>
                      {/* The figure is the content; the bar only ranks it at a
                          glance. Bars alone read as missing data -- five grey
                          rails looked like months that failed to load, when
                          they were months worth zero. */}
                      <TableCell>
                        <span className="flex items-center justify-end gap-2">
                          <span className="bg-muted hidden h-1 w-24 overflow-hidden rounded-full sm:block">
                            <span
                              className="bg-success block h-full rounded-full"
                              style={{ width: `${(entry.earned / peak) * 100}%` }}
                            />
                          </span>
                          <span
                            className={
                              entry.earned > 0
                                ? "w-24 text-right font-medium"
                                : "text-muted-foreground w-24 text-right"
                            }
                          >
                            {formatDH(entry.earned)}
                          </span>
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </section>
          )}

          {capabilities.length > 0 && (
            <section>
              <h3 className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                Compétences — {capabilities.length}, dont {openable.length} sans
                classe ouverte
              </h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10" />
                    <TableHead>Matière</TableHead>
                    <TableHead>Niveau</TableHead>
                    <TableHead>Classe ouverte&nbsp;?</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {capabilitiesPage.visible.map(({ capability, open }) => (
                    <TableRow
                      key={capability.id}
                      className={open ? "text-muted-foreground" : ""}
                    >
                      <TableCell>
                        {/* An open class has nothing to create, so its box is
                            disabled rather than absent: a ragged column is
                            harder to scan than a greyed one. */}
                        <Checkbox
                          disabled={open}
                          checked={selected.has(capability.id)}
                          aria-label={`Ouvrir ${capability.subject_name}`}
                          onCheckedChange={(state) =>
                            setSelected((current) => {
                              const next = new Set(current)
                              if (state === true) next.add(capability.id)
                              else next.delete(capability.id)
                              return next
                            })
                          }
                        />
                      </TableCell>
                      <TableCell className={open ? "" : "font-medium"}>
                        {capability.subject_name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {capabilityLevel(capability)}
                      </TableCell>
                      <TableCell>{open ? "Oui" : "Non"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Pagination
                {...capabilitiesPage}
                shown={capabilitiesPage.visible.length}
                noun="compétences"
              />
              {openable.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <label className="text-muted-foreground flex items-center gap-1.5 text-xs">
                    <Checkbox
                      checked={
                        openable.length > 0 &&
                        openable.every((row) => selected.has(row.capability.id))
                      }
                      onCheckedChange={(state) =>
                        setSelected(
                          state === true
                            ? new Set(openable.map((row) => row.capability.id))
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
            </section>
          )}

          {periods.length > 0 && (
            <section>
              <h3 className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
                Périodes d'enseignement
              </h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Matière</TableHead>
                    <TableHead>Niveau</TableHead>
                    <TableHead>Période</TableHead>
                    <TableHead className="text-right">Nombre</TableHead>
                    <TableHead>Statut</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {periods.map((period) => (
                    <TableRow
                      key={`${period.subject}|${period.level}|${period.wording}`}
                      className={period.ended ? "text-muted-foreground" : ""}
                    >
                      <TableCell className={period.ended ? "" : "font-medium"}>
                        {period.subject}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {period.level}
                      </TableCell>
                      <TableCell>{period.wording}</TableCell>
                      <TableCell className="text-right">
                        {period.count}
                      </TableCell>
                      <TableCell>
                        {period.ended ? "Terminée" : "En cours"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </section>
          )}
        </div>
      )}

      <TeacherDialog
        open={editing}
        onOpenChange={(open) => !open && setEditing(false)}
        initial={profile}
        onSaved={() => {
          setEditing(false)
          setRefresh((count) => count + 1)
          onChanged?.()
        }}
      />

      {departing && profile && (
        <ArchiveTeacherDialog
          teacher={profile}
          teachers={colleagues.filter((row) => row.id !== teacherId)}
          onClose={() => setDeparting(false)}
          onDone={() => {
            setDeparting(false)
            onChanged?.()
            onClose()
          }}
        />
      )}
    </div>
  )
}
