// Matières, the way the owner thinks: per niveau, then per année — « 2ème
// année : Mathématiques, Physique-Chimie » — derived from the real classes.
// No archive here: a matière with zero classes deletes outright (created by
// mistake), one with classes must have them handled first.

import { useCallback, useEffect, useState } from "react"
import { Pencil, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ConfirmButton } from "@/components/Confirm"
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import type { ClassRow, Level, Subject } from "@/lib/api"
import { anneeLabel } from "@/lib/levels"

type Row = Subject & { class_count: number }

export function Subjects() {
  const [levels, setLevels] = useState<Level[]>([])
  const [rows, setRows] = useState<Row[]>([])
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Row | null>(null)

  const reload = useCallback(() => {
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
    apiGet<ClassRow[]>("/api/classes").then(setClasses).catch(() => {})
    apiGet<Row[]>("/api/subjects")
      .then(setRows)
      .catch((err: Error) => setError(err.message))
  }, [])
  useEffect(reload, [reload])

  const deleteSubject = (row: Row) =>
    apiSend("DELETE", `/api/subjects/${row.id}`)
      .then(reload)
      .catch((err: Error) => setError(err.message))

  // The pivot: for one niveau, which matières live in which année —
  // straight from its active classes.
  const anneeLines = (level: Level) => {
    const mine = classes.filter(
      (row) => row.level_id === level.id && row.is_active === 1,
    )
    if (level.teaching_annees === 0) {
      const names = [...new Set(mine.map((row) => row.subject_name))]
      return names.length > 0 ? [{ label: "Bloc unique", names }] : []
    }
    const keyed = new Map<string, { label: string; names: Set<string> }>()
    for (const row of mine) {
      const base = anneeLabel(level.name, row.annee) ?? "Sans année"
      const fork = row.parcours ? ` — ${row.parcours}` : ""
      const key = `${row.annee ?? 0}|${row.parcours ?? ""}`
      if (!keyed.has(key))
        keyed.set(key, { label: `${base}${fork}`, names: new Set() })
      keyed.get(key)!.names.add(row.subject_name)
    }
    return [...keyed.entries()]
      .sort(([a], [b]) => a.localeCompare(b, "fr", { numeric: true }))
      .map(([, line]) => ({ label: line.label, names: [...line.names] }))
  }

  const sections = levels.map((level) => ({
    level,
    entries: rows.filter((row) => row.level_id === level.id),
    lines: anneeLines(level),
  }))

  return (
    <div className="view-enter space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Matières</h2>
        <p className="text-muted-foreground text-sm">
          Chaque matière appartient à son niveau — et vit dans les années où
          ses classes sont ouvertes
        </p>
      </header>

      <Notice message={error} />

      {sections.map(({ level, entries, lines }) => {
        const taught = new Set(lines.flatMap((line) => line.names))
        const idle = entries.filter((row) => !taught.has(row.name))
        return (
          <div key={level.id} className="surface-card p-5">
            <h3 className="mb-3 font-medium">{level.name}</h3>

            {lines.length > 0 && (
              <div className="mb-3 space-y-1.5">
                {lines.map((line) => (
                  <div
                    key={line.label}
                    className="flex flex-wrap items-baseline gap-1.5 text-sm"
                  >
                    <span className="text-muted-foreground w-44 shrink-0">
                      {line.label}
                    </span>
                    <span className="flex flex-wrap gap-1">
                      {line.names.map((name) => (
                        <span
                          key={name}
                          className="bg-secondary text-secondary-foreground rounded-full px-2 py-0.5 text-xs"
                        >
                          {name}
                        </span>
                      ))}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {idle.length > 0 && (
              <div className="mb-3 flex flex-wrap items-baseline gap-1.5 text-sm">
                <span className="text-muted-foreground w-44 shrink-0">
                  Pas encore de classe
                </span>
                <span className="flex flex-wrap gap-1">
                  {idle.map((row) => (
                    <span
                      key={row.id}
                      className="border-border text-muted-foreground rounded-full border border-dashed px-2 py-0.5 text-xs"
                    >
                      {row.name}
                    </span>
                  ))}
                </span>
              </div>
            )}
            {entries.length === 0 && (
              <p className="text-muted-foreground mb-2 text-sm">
                Aucune matière pour ce niveau.
              </p>
            )}

            {entries.length > 0 && (
              <div className="border-border divide-border divide-y rounded-xl border">
                {entries.map((row) => (
                  <div
                    key={row.id}
                    className="flex items-center justify-between gap-3 px-3 py-1.5 text-sm"
                  >
                    <span className="min-w-0 truncate font-medium">{row.name}</span>
                    <span className="flex shrink-0 items-center gap-1">
                      <span className="text-muted-foreground text-xs">
                        {row.class_count > 0
                          ? `${row.class_count} classe(s)`
                          : "aucune classe"}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        title="Renommer"
                        onClick={() => setEditing(row)}
                      >
                        <Pencil className="size-4" />
                      </Button>
                      <ConfirmButton
                        size="sm"
                        variant="ghost"
                        title={
                          row.class_count > 0
                            ? "Suppression refusée tant qu'elle a des classes"
                            : "Supprimer cette matière"
                        }
                        confirmLabel="Supprimer cette matière ?"
                        description="Définitif — réservé aux matières sans aucune classe ; les compétences associées disparaissent aussi."
                        onConfirm={() => deleteSubject(row)}
                      >
                        <Trash2 className="size-4" />
                      </ConfirmButton>
                    </span>
                  </div>
                ))}
              </div>
            )}

            <AddSubject
              levelId={level.id}
              allNames={[...new Set(rows.map((row) => row.name))]}
              onDone={reload}
              onError={setError}
            />
          </div>
        )
      })}

      {editing && (
        <RenameDialog
          target={editing}
          onClose={() => setEditing(null)}
          onDone={() => {
            setEditing(null)
            reload()
          }}
        />
      )}
    </div>
  )
}

function AddSubject({
  levelId,
  allNames,
  onDone,
  onError,
}: {
  levelId: number
  allNames: string[]
  onDone: () => void
  onError: (message: string) => void
}) {
  const [draft, setDraft] = useState("")

  const submit = () => {
    const name = draft.trim()
    if (!name) return
    apiSend("POST", "/api/subjects", { name, level_id: levelId })
      .then(() => {
        setDraft("")
        onDone()
      })
      .catch((err: Error) => onError(err.message))
  }

  return (
    <div className="mt-3 flex items-center gap-2">
      <Input
        list="subject-name-options"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault()
            submit()
          }
        }}
        placeholder="＋ matière…"
        className="w-56"
      />
      <datalist id="subject-name-options">
        {allNames.map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>
      <Button size="sm" variant="outline" onClick={submit} disabled={!draft.trim()}>
        Ajouter
      </Button>
    </div>
  )
}

function RenameDialog({
  target,
  onClose,
  onDone,
}: {
  target: Row
  onClose: () => void
  onDone: () => void
}) {
  const [name, setName] = useState(target.name)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = () => {
    setBusy(true)
    apiSend("PATCH", `/api/subjects/${target.id}`, { name: name.trim() })
      .then(onDone)
      .catch((err: Error) => {
        setNote(err.message)
        setBusy(false)
      })
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Renommer {target.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Label>Nom</Label>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <Notice message={note} />
        <DialogFooter>
          <Button onClick={submit} disabled={busy || !name.trim()}>
            {busy ? "…" : "Enregistrer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
