import { useEffect, useState } from "react"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { apiGet } from "@/lib/api"
import type { ClassSplit, SplitRule } from "@/lib/api"

const WHERE_FROM: Record<ClassSplit["from"], string> = {
  class: "posée sur cette classe",
  teacher: "règle du professeur",
  filiere: "règle de la filière",
  level: "règle du niveau",
  academy: "répartition de l'académie",
}

type Props = {
  teacherId: number | null
  levelId: number | null
  filiere: string | null
  /** La règle choisie pour cette classe seule, ou null pour suivre la
      règle générale. Posée après la création. */
  override: number | null
  onOverride: (ruleId: number | null) => void
}

/**
 * Ce qui s'appliquera à la classe qu'on est en train d'ouvrir.
 *
 * On ne POSE PAS la question : dans l'immense majorité des cas la
 * classe doit suivre la règle générale, et un champ de plus inviterait
 * à poser quinze règles particulières là où une règle de professeur
 * suffisait.
 *
 * Mais le moment où l'on ouvre une classe est celui où l'on pense à
 * l'arrangement passé avec le professeur. On MONTRE donc la
 * conséquence, et on laisse un lien discret pour les vraies exceptions.
 */
export function SplitAtCreation({
  teacherId,
  levelId,
  filiere,
  override,
  onOverride,
}: Props) {
  const [preview, setPreview] = useState<ClassSplit | null>(null)
  const [rules, setRules] = useState<SplitRule[]>([])
  const [choosing, setChoosing] = useState(false)

  useEffect(() => {
    const query = new URLSearchParams()
    if (teacherId !== null) query.set("teacher_id", String(teacherId))
    if (levelId !== null) query.set("level_id", String(levelId))
    if (filiere) query.set("filiere", filiere)
    apiGet<ClassSplit>(`/api/split-preview?${query}`)
      .then(setPreview)
      .catch(() => setPreview(null))
  }, [teacherId, levelId, filiere])

  useEffect(() => {
    if (choosing) apiGet<SplitRule[]>("/api/split-rules").then(setRules).catch(() => {})
  }, [choosing])

  if (!preview) return null
  const chosen = rules.find((rule) => rule.id === override)
  const shown = chosen ?? preview
  const teacherPct = (10000 - shown.venue_bp - shown.owner_bp) / 100

  return (
    <p className="text-muted-foreground text-xs">
      Répartition : salle {shown.venue_bp / 100}% · académie{" "}
      {shown.owner_bp / 100}% · professeur {teacherPct}%
      {" — "}
      {chosen ? `« ${chosen.name} », pour cette classe` : WHERE_FROM[preview.from]}
      {". "}
      {choosing ? (
        <span className="mt-1 flex flex-wrap items-center gap-1">
          <Select
            value={override === null ? "auto" : String(override)}
            onValueChange={(value) =>
              onOverride(value === "auto" ? null : Number(value))
            }
          >
            <SelectTrigger className="h-7 w-52 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="auto">Comme les autres</SelectItem>
              {rules.map((rule) => (
                <SelectItem key={rule.id} value={String(rule.id)}>
                  {rule.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {rules.length === 0 && (
            <span>Aucune répartition particulière n'est encore écrite.</span>
          )}
        </span>
      ) : (
        <button
          type="button"
          className="underline underline-offset-2 hover:text-foreground"
          onClick={() => setChoosing(true)}
        >
          autre répartition
        </button>
      )}
    </p>
  )
}
