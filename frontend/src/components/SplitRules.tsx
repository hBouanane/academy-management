import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ConfirmButton } from "@/components/Confirm"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"
import type { Level, SplitRule, Teacher } from "@/lib/api"

/** Naming the kind alongside the target: a rule on « Moulay Idris » and one
    on « 3ème année » are read the same way otherwise, yet they sit at
    different levels of the precedence chain. */
const SCOPE_LABELS: Record<string, string> = {
  class: "Classe",
  teacher: "Professeur",
  filiere: "Filière",
  level: "Niveau",
}

/**
 * The named splits, and who they apply to.
 *
 * The academy has a reference split -- the one above. But a seasoned
 * teacher is not paid like a beginner, and primaire does not cost what
 * lycee costs. So he writes his rules and says who follows them.
 *
 * The most specific one wins, and the order is fixed: the class, then the
 * teacher, then the filière, then the level, then the reference. It is
 * written on screen, because a precedence you cannot see is a precedence
 * you discover on a payslip.
 */
export function SplitRules({ onError }: { onError: (message: string) => void }) {
  const [rules, setRules] = useState<SplitRule[]>([])
  const [levels, setLevels] = useState<Level[]>([])
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [filieres, setFilieres] = useState<string[]>([])
  const [name, setName] = useState("")
  const [venue, setVenue] = useState("")
  const [owner, setOwner] = useState("")
  const toast = useToast()

  const load = useCallback(
    () =>
      apiGet<SplitRule[]>("/api/split-rules")
        .then(setRules)
        .catch(() => setRules([])),
    [],
  )
  useEffect(() => {
    void load()
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
    apiGet<Teacher[]>("/api/teachers").then(setTeachers).catch(() => {})
    apiGet<string[]>("/api/filieres").then(setFilieres).catch(() => {})
  }, [load])

  const add = () =>
    apiSend("POST", "/api/split-rules", {
      name,
      venue_bp: Math.round(Number(venue) * 100),
      owner_bp: Math.round(Number(owner) * 100),
    })
      .then(() => {
        setName("")
        setVenue("")
        setOwner("")
        toast(`Répartition « ${name} » ajoutée`)
        void load()
      })
      .catch((err: Error) => onError(err.message))

  const nameOf = (scope: string, refId: number | null, refText: string | null) => {
    if (scope === "filiere") return refText ?? "—"
    if (scope === "teacher")
      return teachers.find((entry) => entry.id === refId)?.name ?? "professeur"
    if (scope === "level")
      return levels.find((entry) => entry.id === refId)?.name ?? "niveau"
    return `classe n° ${refId}`
  }

  const apply = (ruleId: number, scope: string, ref: string) =>
    apiSend("POST", `/api/split-rules/${ruleId}/applies-to`, {
      scope,
      ...(scope === "filiere" ? { ref_text: ref } : { ref_id: Number(ref) }),
    })
      .then(load)
      .catch((err: Error) => onError(err.message))

  const unapply = (scope: string, refId: number | null, refText: string | null) =>
    apiSend("DELETE", `/api/split-rules/applies-to/${scope}/${refText ?? refId}`)
      .then(load)
      .catch((err: Error) => onError(err.message))

  // Two shares entered are enough to announce the third; the name only
  // concerns the button.
  const partsFilled =
    venue.trim() !== "" &&
    owner.trim() !== "" &&
    Number.isFinite(Number(venue)) &&
    Number.isFinite(Number(owner)) &&
    Number(venue) >= 0 &&
    Number(owner) >= 0 &&
    Number(venue) + Number(owner) <= 100

  const valid =
    name.trim() !== "" &&
    Number(venue) >= 0 &&
    Number(owner) >= 0 &&
    Number(venue) + Number(owner) <= 100

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Répartitions particulières</Label>
        <p className="text-muted-foreground text-xs">
          La répartition ci-dessus s'applique partout — sauf là où vous en
          posez une autre. Quand plusieurs pourraient convenir, c'est la plus
          précise qui gagne : <strong>la classe</strong>, puis{" "}
          <strong>le professeur</strong>, puis <strong>la filière</strong>,
          puis <strong>le niveau</strong>.
        </p>
      </div>

      {rules.map((rule) => (
        <div key={rule.id} className="border-border space-y-2 rounded-xl border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{rule.name}</span>
            <span className="text-muted-foreground text-sm">
              salle {rule.venue_bp / 100}% · académie {rule.owner_bp / 100}% ·
              professeur {(10000 - rule.venue_bp - rule.owner_bp) / 100}%
            </span>
            <span className="flex-1" />
            <ConfirmButton
              size="sm"
              variant="ghost"
              title="Supprimer cette répartition"
              confirmLabel="Supprimer ?"
              description="Les classes qui la suivaient reprendront la répartition du niveau, ou celle de l'académie. Les mois déjà encaissés ne bougent pas."
              onConfirm={() =>
                apiSend("DELETE", `/api/split-rules/${rule.id}`)
                  .then(load)
                  .catch((err: Error) => onError(err.message))
              }
            >
              <Trash2 className="size-4" />
            </ConfirmButton>
          </div>

          {/* One target per line, with its kind named. As a chip cloud, « 3ème
              année » and « Moulay Idris » looked alike, so a rule applying to
              a level and one applying to a teacher were indistinguishable --
              which is precisely what decides who wins the precedence. */}
          <div className="space-y-1">
            {rule.applies_to.map((target) => (
              <div
                key={`${target.scope}-${target.ref_id}-${target.ref_text}`}
                className="flex items-center gap-2 text-sm"
              >
                <span className="text-muted-foreground w-20 shrink-0 text-xs">
                  {SCOPE_LABELS[target.scope] ?? target.scope}
                </span>
                <span>
                  {nameOf(target.scope, target.ref_id, target.ref_text)}
                </span>
                <button
                  type="button"
                  title="Ne plus appliquer ici"
                  className="text-muted-foreground hover:text-foreground"
                  onClick={() =>
                    unapply(target.scope, target.ref_id, target.ref_text)
                  }
                >
                  <X className="size-3" />
                </button>
              </div>
            ))}
            {rule.applies_to.length === 0 && (
              <span className="text-muted-foreground text-xs">
                Ne s'applique nulle part pour l'instant.
              </span>
            )}
            <Applier
              teachers={teachers}
              levels={levels}
              filieres={filieres}
              onApply={(scope, ref) => apply(rule.id, scope, ref)}
            />
          </div>
        </div>
      ))}

      <div className="border-border flex flex-wrap items-end gap-2 rounded-xl border border-dashed p-3">
        <div className="space-y-1.5">
          <Label htmlFor="rule-name">Nom</Label>
          <Input
            id="rule-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Prof senior"
            className="h-8 w-44 text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rule-venue">Salle (%)</Label>
          <Input
            id="rule-venue"
            value={venue}
            onChange={(event) => setVenue(event.target.value)}
            className="h-8 w-24 text-sm"
            inputMode="decimal"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rule-owner">Académie (%)</Label>
          <Input
            id="rule-owner"
            value={owner}
            onChange={(event) => setOwner(event.target.value)}
            className="h-8 w-24 text-sm"
            inputMode="decimal"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-muted-foreground">Professeurs</Label>
          <div className="border-border text-muted-foreground flex h-8 w-44 items-center rounded-lg border border-dashed px-3 text-sm">
            {partsFilled
              ? `${100 - Number(venue) - Number(owner)}% (partagé par matière)`
              : "—"}
          </div>
        </div>
        <Button size="sm" disabled={!valid} onClick={add}>
          <Plus className="size-4" />
          Ajouter
        </Button>
      </div>
    </div>
  )
}

/** Say who a rule applies to -- a teacher, a filière, a level. */
function Applier({
  teachers,
  levels,
  filieres,
  onApply,
}: {
  teachers: Teacher[]
  levels: Level[]
  filieres: string[]
  onApply: (scope: string, ref: string) => void
}) {
  const [scope, setScope] = useState("teacher")
  const choices =
    scope === "teacher"
      ? teachers.map((entry) => [String(entry.id), entry.name] as const)
      : scope === "level"
        ? levels.map((entry) => [String(entry.id), entry.name] as const)
        : filieres.map((entry) => [entry, entry] as const)

  return (
    <span className="flex flex-wrap items-center gap-1">
      <Select value={scope} onValueChange={setScope}>
        <SelectTrigger className="h-7 w-32 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="teacher">Un professeur</SelectItem>
          <SelectItem value="level">Un niveau</SelectItem>
          <SelectItem value="filiere">Une filière</SelectItem>
        </SelectContent>
      </Select>
      <Select value="" onValueChange={(value) => onApply(scope, value)}>
        <SelectTrigger className="h-7 w-40 text-xs">
          <SelectValue placeholder="Appliquer à…" />
        </SelectTrigger>
        <SelectContent>
          {choices.map(([value, label]) => (
            <SelectItem key={value} value={value}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </span>
  )
}
