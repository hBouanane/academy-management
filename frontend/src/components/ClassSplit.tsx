import { useCallback, useEffect, useState } from "react"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"
import type { ClassSplit as Resolved, SplitRule } from "@/lib/api"

const WHERE_FROM: Record<Resolved["from"], string> = {
  class: "posée sur cette classe",
  teacher: "règle du professeur",
  filiere: "règle de la filière",
  level: "règle du niveau",
  academy: "répartition de l'académie",
}

/**
 * La répartition de CETTE classe.
 *
 * Elle suit la chaîne — professeur, filière, niveau, académie — sauf
 * si on en pose une ici. L'écran dit toujours d'où vient le chiffre :
 * « pourquoi la salle prend-elle 30 % sur ce cours ? » doit avoir une
 * réponse immédiate, sinon on se met à douter des comptes.
 */
export function ClassSplit({ classId }: { classId: number }) {
  const [resolved, setResolved] = useState<Resolved | null>(null)
  const [rules, setRules] = useState<SplitRule[]>([])
  const toast = useToast()

  const load = useCallback(
    () =>
      Promise.all([
        apiGet<Resolved>(`/api/classes/${classId}/split`),
        apiGet<SplitRule[]>("/api/split-rules"),
      ])
        .then(([found, all]) => {
          setResolved(found)
          setRules(all)
        })
        .catch(() => setResolved(null)),
    [classId],
  )
  useEffect(() => {
    void load()
  }, [load])

  if (!resolved) return null

  const posed = rules.find((rule) =>
    rule.applies_to.some(
      (target) => target.scope === "class" && target.ref_id === classId,
    ),
  )

  const choose = (value: string) => {
    const call =
      value === "auto"
        ? apiSend("DELETE", `/api/split-rules/applies-to/class/${classId}`)
        : apiSend("POST", `/api/split-rules/${value}/applies-to`, {
            scope: "class",
            ref_id: classId,
          })
    call
      .then(() => {
        toast(
          value === "auto"
            ? "Cette classe suit de nouveau la règle générale"
            : "Répartition posée sur cette classe",
        )
        void load()
      })
      .catch((err: Error) => toast(err.message, "error"))
  }

  const teacherPct = (10000 - resolved.venue_bp - resolved.owner_bp) / 100

  return (
    <div>
      <p className="text-muted-foreground mb-1.5 text-xs font-medium tracking-wide uppercase">
        Répartition de l'argent
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={posed ? String(posed.id) : "auto"} onValueChange={choose}>
          <SelectTrigger className="h-8 w-56 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">Comme les autres (automatique)</SelectItem>
            {rules.map((rule) => (
              <SelectItem key={rule.id} value={String(rule.id)}>
                {rule.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-muted-foreground text-sm">
          salle {resolved.venue_bp / 100}% · académie {resolved.owner_bp / 100}% ·
          professeur {teacherPct}%
        </span>
      </div>
      <p className="text-muted-foreground mt-1 text-xs">
        {resolved.rule_name
          ? `« ${resolved.rule_name} » — ${WHERE_FROM[resolved.from]}`
          : WHERE_FROM[resolved.from]}
        . Les mois déjà encaissés gardent leur partage.
      </p>
    </div>
  )
}
