// THE tree (the client's sketch): one stacked section per niveau, année rows
// inside (3ème collège forks Normal / Râ'ida), matière chips on every row.
// One single add-field per row: type to reuse an existing matière or create
// a new one with Entrée. « Ajouter un niveau » grows the tree itself.
//
// Two modes: "check" (professor capabilities — checkbox chips) and "pick"
// (choose ONE slot for a class — the parcours fork gains a third "classe
// commune" row that groups Normal + Râ'ida together).

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

export type TreeSlot = {
  level_id: number
  annee: number | null
  parcours: string | null
  subject_id: number
}

export const slotKey = (slot: Omit<TreeSlot, "subject_id">, subjectId: number) =>
  `${slot.level_id}|${slot.annee ?? ""}|${slot.parcours ?? ""}|${subjectId}`

type Node = {
  level: Level
  label: string
  annee: number | null
  parcours: string | null
  commun?: boolean
}

const levelNodes = (level: Level, mode: "check" | "pick"): Node[] => {
  const annees = teachingAnnees(level)
  if (annees.length === 0)
    return [{ level, label: "", annee: null, parcours: null }]
  return annees.flatMap(([value, label]): Node[] => {
    const forks = parcoursOptions(level.name, value)
    if (forks.length === 0)
      return [{ level, label, annee: Number(value), parcours: null }]
    const rows: Node[] = forks.map((fork) => ({
      level,
      label: `${label} — ${fork}`,
      annee: Number(value),
      parcours: fork,
    }))
    if (mode === "pick")
      rows.push({
        level,
        label: `${label} — classe commune (${forks.join(" + ")})`,
        annee: Number(value),
        parcours: null,
        commun: true,
      })
    return rows
  })
}

type Props = {
  mode: "check" | "pick"
  levels: Level[]
  subjects: Subject[]
  /** check mode: the set of checked slot keys. */
  checked?: Set<string>
  onToggle?: (slots: { key: string; subjectId: number }[], on: boolean) => void
  /** pick mode: the selected slot. */
  picked?: TreeSlot | null
  onPick?: (slot: TreeSlot) => void
  /** Called after a matière or niveau was created here (refetch lists). */
  onGrown: () => void
}

export function ProgramTree({
  mode,
  levels,
  subjects,
  checked,
  onToggle,
  picked,
  onPick,
  onGrown,
}: Props) {
  const [error, setError] = useState<string | null>(null)

  return (
    <div className="space-y-4">
      <Notice message={error} />
      {levels.map((level) => {
        const nodes = levelNodes(level, mode)
        return (
          <div key={level.id} className="border-border rounded-xl border p-3">
            <p className="mb-2 text-sm font-semibold">{level.name}</p>
            <div className="space-y-2.5">
              {nodes.map((node) => (
                <NodeRow
                  key={`${node.label}|${node.commun ?? false}`}
                  node={node}
                  mode={mode}
                  subjects={subjects}
                  checked={checked}
                  onToggle={onToggle}
                  picked={picked}
                  onPick={onPick}
                  onGrown={onGrown}
                  onError={setError}
                />
              ))}
            </div>
          </div>
        )
      })}
      <AddLevel onGrown={onGrown} onError={setError} />
    </div>
  )
}

function NodeRow({
  node,
  mode,
  subjects,
  checked,
  onToggle,
  picked,
  onPick,
  onGrown,
  onError,
}: {
  node: Node
  mode: "check" | "pick"
  subjects: Subject[]
  checked?: Set<string>
  onToggle?: (slots: { key: string; subjectId: number }[], on: boolean) => void
  picked?: TreeSlot | null
  onPick?: (slot: TreeSlot) => void
  onGrown: () => void
  onError: (message: string) => void
}) {
  const [draft, setDraft] = useState("")
  const coords = {
    level_id: node.level.id,
    annee: node.annee,
    parcours: node.parcours,
  }

  const isPicked = (subjectId: number) =>
    picked !== null &&
    picked !== undefined &&
    picked.level_id === coords.level_id &&
    picked.annee === coords.annee &&
    picked.parcours === coords.parcours &&
    picked.subject_id === subjectId

  const chipFor = (subject: Subject) => {
    const key = slotKey(coords, subject.id)
    const active = mode === "check" ? checked?.has(key) : isPicked(subject.id)
    return (
      <button
        key={subject.id}
        type="button"
        onClick={() =>
          mode === "check"
            ? onToggle?.([{ key, subjectId: subject.id }], !checked?.has(key))
            : onPick?.({ ...coords, subject_id: subject.id })
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
  }

  const addSubject = async () => {
    const name = draft.trim()
    if (!name) return
    const existing = subjects.find(
      (subject) => subject.name.toLowerCase() === name.toLowerCase(),
    )
    try {
      const id = existing
        ? existing.id
        : (await apiSend<{ id: number }>("POST", "/api/subjects", { name })).id
      setDraft("")
      onGrown()
      if (mode === "check") onToggle?.([{ key: slotKey(coords, id), subjectId: id }], true)
      else onPick?.({ ...coords, subject_id: id })
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
        {subjects.map(chipFor)}
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
          {subjects.map((subject) => (
            <option key={subject.id} value={subject.name} />
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
