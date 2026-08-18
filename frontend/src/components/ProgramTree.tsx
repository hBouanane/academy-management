// THE tree (the client's sketch): one stacked section per niveau, année rows
// inside (3ème collège forks Normal / Râ'ida), matière chips on every row —
// but each niveau shows ONLY ITS OWN matières. The single add-field per row
// reuses this niveau's matière or creates it here (typing a name that exists
// elsewhere creates this niveau's own copy). « Ajouter un niveau » grows the
// tree itself. Used to declare what a professor can teach.

import { useState } from "react"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Notice } from "@/components/Notice"
import { apiSend } from "@/lib/api"
import type { Level, Subject } from "@/lib/api"
import { parcoursOptions, teachingAnnees } from "@/lib/levels"
import { useAlert } from "@/lib/alert"

export const slotKey = (
  slot: { level_id: number; annee: number | null; parcours: string | null },
  subjectId: number,
) => `${slot.level_id}|${slot.annee ?? ""}|${slot.parcours ?? ""}|${subjectId}`

type Node = {
  level: Level
  label: string
  annee: number | null
  parcours: string | null
}

const levelNodes = (level: Level): Node[] => {
  const annees = teachingAnnees(level)
  if (annees.length === 0)
    return [{ level, label: "", annee: null, parcours: null }]
  return annees.flatMap(([value, label]): Node[] => {
    const forks = parcoursOptions(level.name, value)
    if (forks.length === 0)
      return [{ level, label, annee: Number(value), parcours: null }]
    return forks.map((fork) => ({
      level,
      label: `${label} — ${fork}`,
      annee: Number(value),
      parcours: fork,
    }))
  })
}

// A niveau shows its own matières (plus legacy unscoped ones).
export const subjectsOfLevel = (subjects: Subject[], levelId: number) =>
  subjects.filter(
    (subject) => subject.level_id === levelId || subject.level_id === null,
  )

type Props = {
  levels: Level[]
  subjects: Subject[]
  checked: Set<string>
  onToggle: (slots: { key: string; subjectId: number }[], on: boolean) => void
  /** Called after a matière or niveau was created here (refetch lists). */
  onGrown: () => void
}

export function ProgramTree({ levels, subjects, checked, onToggle, onGrown }: Props) {
  const [error, setError] = useAlert()

  return (
    <div className="space-y-4">
      <Notice alert={error} />
      {levels.map((level) => (
        <div key={level.id} className="border-border rounded-xl border p-3">
          <p className="mb-2 text-sm font-semibold">{level.name}</p>
          <div className="space-y-2.5">
            {levelNodes(level).map((node) => (
              <NodeRow
                key={node.label || "bloc"}
                node={node}
                subjects={subjectsOfLevel(subjects, level.id)}
                allNames={[...new Set(subjects.map((subject) => subject.name))]}
                checked={checked}
                onToggle={onToggle}
                onGrown={onGrown}
                onError={setError}
              />
            ))}
          </div>
        </div>
      ))}
      <AddLevel onGrown={onGrown} onError={setError} />
    </div>
  )
}

function NodeRow({
  node,
  subjects,
  allNames,
  checked,
  onToggle,
  onGrown,
  onError,
}: {
  node: Node
  subjects: Subject[]
  allNames: string[]
  checked: Set<string>
  onToggle: (slots: { key: string; subjectId: number }[], on: boolean) => void
  onGrown: () => void
  onError: (message: string) => void
}) {
  const [draft, setDraft] = useState("")
  const coords = {
    level_id: node.level.id,
    annee: node.annee,
    parcours: node.parcours,
  }

  const addSubject = async () => {
    const name = draft.trim()
    if (!name) return
    const mine = subjects.find(
      (subject) => subject.name.toLowerCase() === name.toLowerCase(),
    )
    try {
      // Same name in ANOTHER niveau? Creating here IS the copy.
      const id = mine
        ? mine.id
        : (
            await apiSend<{ id: number }>("POST", "/api/subjects", {
              name,
              level_id: node.level.id,
            })
          ).id
      setDraft("")
      onGrown()
      onToggle([{ key: slotKey(coords, id), subjectId: id }], true)
    } catch (err) {
      onError((err as Error).message)
    }
  }

  return (
    <div className={node.label ? "pl-3" : ""}>
      {node.label && (
        <p className="text-muted-foreground mb-1 text-xs font-medium">
          {node.label}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        {subjects.map((subject) => {
          const key = slotKey(coords, subject.id)
          const active = checked.has(key)
          return (
            <button
              key={subject.id}
              type="button"
              onClick={() =>
                onToggle([{ key, subjectId: subject.id }], !active)
              }
              className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                active
                  ? "border-transparent bg-primary text-primary-foreground"
                  : "border-border text-muted-foreground hover:border-foreground/40"
              }`}
            >
              {active ? "✓ " : ""}
              {subject.name}
            </button>
          )
        })}
        <Input
          list="tree-subject-options"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault()
              void addSubject()
            }
          }}
          placeholder="＋ matière…"
          className="h-7 w-32 text-xs"
        />
        <datalist id="tree-subject-options">
          {allNames.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </div>
    </div>
  )
}

function AddLevel({
  onGrown,
  onError,
}: {
  onGrown: () => void
  onError: (message: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [structure, setStructure] = useState("0")
  const [count, setCount] = useState("3")

  if (!open)
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Plus className="size-4" /> Ajouter un niveau
      </Button>
    )

  const submit = () => {
    apiSend("POST", "/api/levels", {
      name: name.trim(),
      teaching_annees: structure === "0" ? 0 : Number(count),
    })
      .then(() => {
        setOpen(false)
        setName("")
        onGrown()
      })
      .catch((err: Error) => onError(err.message))
  }

  return (
    <div className="border-border flex flex-wrap items-center gap-2 rounded-xl border border-dashed p-3">
      <Input
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Nom du niveau (Soutien, Langues…)"
        className="min-w-44 flex-1"
      />
      <Select value={structure} onValueChange={setStructure}>
        <SelectTrigger className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="0">Bloc unique</SelectItem>
          <SelectItem value="n">Par années</SelectItem>
        </SelectContent>
      </Select>
      {structure === "n" && (
        <Input
          type="number"
          min="1"
          max="12"
          value={count}
          onChange={(event) => setCount(event.target.value)}
          className="w-20"
        />
      )}
      <Button size="sm" onClick={submit} disabled={!name.trim()}>
        Créer
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
        Annuler
      </Button>
    </div>
  )
}
