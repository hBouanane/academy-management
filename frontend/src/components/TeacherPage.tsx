// One professor, whole story: classes with student counts and what each one
// actually paid him, capabilities, six-month history, assignment periods.
//
// Une PAGE, plus une fenetre. Six sections empilees dans une modale
// donnaient un mur : on ne savait plus ou regarder, et la moitie etait
// sous la ligne de flottaison. En pleine largeur, chaque chose a sa
// place et son air.
//
// Deuxieme passe : la place ne suffit pas si tout se vaut. Un professeur
// avec douze classes en montrait onze a « 0 · 0,00 DH » ; la seule qui
// rapportait se perdait au milieu. Ce qui rapporte passe devant, le
// reste se replie, et les lignes qui se repetent se comptent au lieu de
// se suivre.

import { useEffect, useMemo, useState } from "react"
import { ArrowLeft } from "lucide-react"
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
import { Field, FieldGrid } from "@/components/Field"
import { monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import type { TeacherProfile as Profile } from "@/lib/api"
import { segmentLabel } from "@/lib/levels"
import { formatDH } from "@/lib/money"
import { useAlert } from "@/lib/alert"

const capabilityLabel = (capability: Profile["capabilities"][number]) =>
  `${capability.subject_name} · ${capability.level_name}${
    capability.annee ? ` ${capability.annee}` : ""
  }${capability.parcours ? ` ${capability.parcours}` : ""}`

/** Un titre de section, toujours de la meme facon. */
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
      {children}
    </p>
  )
}

type Props = {
  teacherId: number
  month: string
  onClose: () => void
  onChanged?: () => void
}

export function TeacherPage({ teacherId, month, onClose, onChanged }: Props) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useAlert()
  const [refresh, setRefresh] = useState(0)
  // Batch class creation: check several capabilities, one « Créer » click.
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [showDormant, setShowDormant] = useState(false)
  const [showTaught, setShowTaught] = useState(false)

  useEffect(() => {
    setError(null)
    apiGet<Profile>(`/api/teachers/${teacherId}/profile?month=${month}`)
      .then(setProfile)
      .catch((err: Error) => setError(err.message))
  }, [teacherId, month, refresh, setError])

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
  const taught = (profile?.capabilities ?? []).filter(alreadyTeaches)

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

  // Une classe qui n a ni inscrit ni recette n apprend rien sur ce mois :
  // elle existe, c est tout. On la garde -- il doit pouvoir la retrouver --
  // mais derriere une ligne, pas devant celle qui rapporte.
  const { active, dormant } = useMemo(() => {
    const rows = profile?.classes ?? []
    return {
      active: rows.filter(
        (row) => row.enrolled_count > 0 || row.earned_centimes > 0,
      ),
      dormant: rows.filter(
        (row) => row.enrolled_count === 0 && row.earned_centimes === 0,
      ),
    }
  }, [profile])

  // « francais · Collège — depuis le début (en cours) », treize fois de
  // suite, ne se lit pas : les lignes identiques se comptent.
  const periods = useMemo(() => {
    const grouped = new Map<
      string,
      { label: string; span: string; ended: boolean; count: number }
    >()
    for (const item of profile?.assignments ?? []) {
      const label = `${item.subject_name} · ${item.level_name}`
      // « depuis le début au 2026-08-01 » ne se dit pas : chaque cas a sa
      // tournure, sinon on lit une phrase cassée.
      const span = item.from_date
        ? item.to_date
          ? `du ${item.from_date} au ${item.to_date}`
          : `depuis le ${item.from_date}`
        : item.to_date
          ? `jusqu'au ${item.to_date}`
          : "depuis le début"
      const key = `${label}|${span}`
      const seen = grouped.get(key)
      if (seen) seen.count += 1
      else
        grouped.set(key, { label, span, ended: Boolean(item.to_date), count: 1 })
    }
    const all = [...grouped.values()]
    return { current: all.filter((p) => !p.ended), past: all.filter((p) => p.ended) }
  }, [profile])

  const peak = Math.max(...(profile?.history ?? []).map((e) => e.earned), 1)

  // Le total des classes et le total du mois peuvent differer : une avance
  // versee sur une inscription ne passe par aucun paiement, donc par aucune
  // classe. La difference existait deja -- elle etait seulement invisible.
  // Un chiffre qui contredit celui du haut sans un mot fait douter de toute
  // la page ; on le nomme.
  const classesSum = active.reduce((sum, row) => sum + row.earned_centimes, 0)
  const unattached = monthTotal - classesSum

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button size="sm" variant="ghost" onClick={onClose}>
            <ArrowLeft className="size-4" />
            Retour
          </Button>
          <div>
            <h2 className="text-2xl font-medium tracking-tight">
              {profile?.name ?? "Professeur"}
            </h2>
            <p className="text-muted-foreground text-sm">
              {profile?.is_owner ? "Propriétaire + professeur" : "Professeur"}
              {" · "}
              {monthLabel(month)}
            </p>
          </div>
        </div>
      </header>
      <Notice alert={error} />
      {profile && (
        <div className="space-y-6">
          {/* Le rôle est déjà écrit sous son nom : le répéter ici volait
              une case à ce qu'on vient vraiment lire, l'argent. */}
          <FieldGrid>
            <Field label="Téléphone">{profile.phone ?? "—"}</Field>
            <Field label="Depuis le">
              {profile.created_at?.slice(0, 10) ?? "—"}
            </Field>
            <Field label={`Gagné comme professeur — ${monthLabel(month)}`}>
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

          {/* Le tableau ne prend plus toute la largeur : entre le nom de la
              classe et sa recette, l'oeil avait un mètre à parcourir. */}
          <div className="max-w-4xl">
            <SectionTitle>Classes qui ont rapporté ce mois-ci</SectionTitle>
            {profile.classes.length === 0 && (
              <p className="text-muted-foreground text-sm">Aucune classe.</p>
            )}
            {profile.classes.length > 0 && active.length === 0 && (
              <p className="text-muted-foreground text-sm">
                Aucun inscrit en {monthLabel(month).toLowerCase()}.
              </p>
            )}
            {active.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Classe</TableHead>
                    <TableHead>Segment</TableHead>
                    <TableHead className="text-right">Inscrits</TableHead>
                    <TableHead className="text-right">
                      Gagné ({monthLabel(month)})
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {active.map((row) => (
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
                      <TableCell className="text-right">
                        {row.enrolled_count}
                      </TableCell>
                      <TableCell className="text-right font-medium">
                        {formatDH(row.earned_centimes)}
                      </TableCell>
                    </TableRow>
                  ))}
                  {active.length > 1 && (
                    <TableRow>
                      <TableCell colSpan={2} className="text-muted-foreground">
                        Total des classes
                      </TableCell>
                      <TableCell className="text-right">
                        {active.reduce((sum, r) => sum + r.enrolled_count, 0)}
                      </TableCell>
                      <TableCell className="text-right font-semibold">
                        {formatDH(classesSum)}
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            )}

            {active.length > 0 && unattached !== 0 && (
              <p className="text-muted-foreground mt-1.5 text-xs">
                {formatDH(Math.abs(unattached))}{" "}
                {unattached > 0 ? "de plus" : "de moins"} sur son total du mois
                — une avance versée sur une inscription ne passe par aucune
                classe.
              </p>
            )}

            {dormant.length > 0 && (
              <div className="mt-2">
                <button
                  type="button"
                  onClick={() => setShowDormant((open) => !open)}
                  className="text-muted-foreground hover:text-foreground text-xs underline-offset-2 hover:underline"
                >
                  {showDormant ? "Masquer" : "Afficher"} les {dormant.length}{" "}
                  classes sans inscrit ce mois-ci
                </button>
                {showDormant && (
                  <div className="text-muted-foreground mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                    {dormant.map((row) => (
                      <span key={row.id}>
                        {row.subject_name}
                        <span className="text-xs"> · {segmentLabel(row)}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="grid max-w-5xl gap-6 sm:grid-cols-2">
            <div>
              <SectionTitle>6 derniers mois</SectionTitle>
              {/* Six montants alignés se ressemblaient tous. Une barre
                  montre d'un coup le mois qui sort du lot. */}
              <div className="space-y-1">
                {profile.history.map((entry) => (
                  <div key={entry.month} className="flex items-center gap-2">
                    <span className="text-muted-foreground w-24 shrink-0 text-sm capitalize">
                      {monthLabel(entry.month)}
                    </span>
                    <span className="bg-muted h-1.5 flex-1 overflow-hidden rounded-full">
                      <span
                        className="bg-success block h-full rounded-full"
                        style={{ width: `${(entry.earned / peak) * 100}%` }}
                      />
                    </span>
                    <span
                      className={`w-24 shrink-0 text-right text-sm ${
                        entry.earned > 0
                          ? "font-medium"
                          : "text-muted-foreground"
                      }`}
                    >
                      {entry.earned > 0 ? formatDH(entry.earned) : "—"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <SectionTitle>Compétences</SectionTitle>
              {/* Deux états lisibles sans pictogramme : la classe ouverte
                    est une pastille pleine et calme, celle qui manque garde
                    sa case à cocher. */}
              {openable.length > 0 && (
                <>
                  <p className="text-muted-foreground mb-1.5 text-xs">
                    Il peut les enseigner, la classe n'existe pas encore —
                    cochez pour l'ouvrir
                  </p>
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
                  <div className="mb-3 flex flex-wrap items-center gap-2">
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
                </>
              )}
              {/* Ces compétences-là ont déjà leur classe : elles figurent
                  toutes dans le tableau du dessus. Les répéter en pastilles
                  faisait relire douze fois la même chose. */}
              {taught.length > 0 && (
                <>
                  <button
                    type="button"
                    onClick={() => setShowTaught((open) => !open)}
                    className="text-muted-foreground hover:text-foreground text-xs underline-offset-2 hover:underline"
                  >
                    {taught.length} déjà ouverte{taught.length > 1 ? "s" : ""} —{" "}
                    {showTaught ? "masquer" : "afficher"}
                  </button>
                  {showTaught && (
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {taught.map((cap) => (
                        <span
                          key={cap.id}
                          className="bg-secondary text-secondary-foreground rounded-full px-2.5 py-0.5 text-xs"
                        >
                          {capabilityLabel(cap)}
                        </span>
                      ))}
                    </div>
                  )}
                </>
              )}
              {profile.capabilities.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  Aucune — modifiez le professeur pour cocher son arbre.
                </p>
              )}
            </div>
          </div>

          {profile.assignments.length > 0 && (
            <div className="max-w-4xl">
              <SectionTitle>Périodes d'enseignement</SectionTitle>
              {periods.current.length > 0 && (
                <div className="text-muted-foreground flex flex-wrap gap-x-5 gap-y-1 text-sm">
                  {periods.current.map((p) => (
                    <span key={`${p.label}|${p.span}`}>
                      {p.label}
                      {p.count > 1 && (
                        <span className="text-xs"> ×{p.count}</span>
                      )}
                      <span className="text-xs"> — {p.span}</span>
                    </span>
                  ))}
                </div>
              )}
              {/* Une periode terminee dit quelque chose : elle explique
                  pourquoi un mois s arrete. Elle ne se noie plus parmi
                  celles qui courent toujours. */}
              {periods.past.length > 0 && (
                <div className="mt-2">
                  <p className="text-muted-foreground text-xs">Terminées</p>
                  <div className="text-muted-foreground flex flex-wrap gap-x-5 gap-y-1 text-sm">
                    {periods.past.map((p) => (
                      <span key={`${p.label}|${p.span}`}>
                        {p.label}
                        {p.count > 1 && (
                          <span className="text-xs"> ×{p.count}</span>
                        )}
                        <span className="text-xs"> — {p.span}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
