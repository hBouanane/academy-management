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
  /** The rule chosen for this class alone, or null to follow the general
      rule. Set after creation. */
  override: number | null
  onOverride: (ruleId: number | null) => void
}

/**
 * What will apply to the class currently being opened.
 *
 * We do NOT ask the question: in the vast majority of cases the class
 * should follow the general rule, and one more field would invite fifteen
 * particular rules where a single teacher rule would have done.
 *
 * But the moment a class is opened is the moment one thinks about the
 * arrangement made with the teacher. So we SHOW the consequence, and
 * leave a discreet link for the genuine exceptions.
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
