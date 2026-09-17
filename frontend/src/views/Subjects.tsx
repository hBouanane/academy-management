// Matières, the way the owner thinks: per niveau, then per année — « 2ème
// année : Mathématiques, Physique-Chimie » — derived from the real classes.
// No archive here: a matière with zero classes deletes outright (created by
// mistake), one with classes must have them handled first.

import { useCallback, useEffect, useRef, useState } from "react"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import type { ClassRow, Level, Subject } from "@/lib/api"
import { anneeLabel } from "@/lib/levels"
import { useAlert } from "@/lib/alert"
import { useToast } from "@/components/Toast"

type Row = Subject & { class_count: number; archived_class_count: number }

/** Primaire's single matière: one group, helped with everything. */
const ACCOMPAGNEMENT = "Accompagnement complet"

export function Subjects() {
  const [levels, setLevels] = useState<Level[]>([])
  const [rows, setRows] = useState<Row[]>([])
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [error, setError] = useAlert()
  // The matière created just now: it pulses long enough to be spotted.
  const [justAdded, setJustAdded] = useState<number | null>(null)
  const toast = useToast()
  const [editing, setEditing] = useState<Row | null>(null)

  useEffect(() => {
    if (justAdded === null) return
    const timer = window.setTimeout(() => setJustAdded(null), 1400)
    return () => window.clearTimeout(timer)
  }, [justAdded])

  const reload = useCallback(() => {
    setError(null)
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
    apiGet<ClassRow[]>("/api/classes").then(setClasses).catch(() => {})
    apiGet<Row[]>("/api/subjects")
      .then(setRows)
      .catch((err: Error) => setError(err.message))
  }, [setError])
  useEffect(reload, [reload])

  const deleteSubject = (row: Row) =>
    apiSend("DELETE", `/api/subjects/${row.id}`)
      .then(reload)
      .catch((err: Error) => setError(err.message))

  // The pivot: for one niveau, which matières live in which année —
  // straight from its active classes. Each chip IS the matière: rename in
  // place, delete on the ones no class uses (no separate list, no doubles).
  const anneeLines = (level: Level, entries: Row[]) => {
    const byId = new Map(entries.map((row) => [row.id, row]))
    const mine = classes.filter(
      (row) => row.level_id === level.id && row.is_active === 1,
    )
    const keyed = new Map<string, { label: string; ids: Set<number> }>()
    for (const row of mine) {
      const key =
        level.teaching_annees === 0
          ? "bloc"
          : `${row.annee ?? 0}|${row.parcours ?? ""}`
      if (!keyed.has(key)) {
        const base =
          level.teaching_annees === 0
            ? "Bloc unique"
            : (anneeLabel(level.name, row.annee) ?? "Sans année")
        const fork = row.parcours ? ` — ${row.parcours}` : ""
        keyed.set(key, { label: `${base}${fork}`, ids: new Set() })
      }
      keyed.get(key)!.ids.add(row.subject_id)
    }
    return [...keyed.entries()]
      .sort(([a], [b]) => a.localeCompare(b, "fr", { numeric: true }))
      .map(([, line]) => ({
        label: line.label,
        subjects: [...line.ids]
          .map((id) => byId.get(id))
          .filter((row): row is Row => row !== undefined),
      }))
  }

  const sections = levels.map((level) => {
    const entries = rows.filter((row) => row.level_id === level.id)
    const lines = anneeLines(level, entries)
    // Same lines, read the other way round: the matière is the row, and the
    // années where it lives are one of its columns.
    const anneesOf = new Map<number, string[]>()
    for (const line of lines) {
      for (const subject of line.subjects) {
        anneesOf.set(subject.id, [
          ...(anneesOf.get(subject.id) ?? []),
          line.label,
        ])
      }
    }
    return { level, entries, lines, anneesOf }
  })

  return (
    <div className="view-enter space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Matières</h2>
        <p className="text-muted-foreground text-sm">
          Chaque matière appartient à son niveau — et vit dans les années où
          ses classes sont ouvertes
        </p>
      </header>

      <Notice alert={error} />

      {sections.map(({ level, entries, anneesOf }) => {
        return (
          <div key={level.id} className="surface-card p-5">
            <h3 className="mb-3 font-medium">{level.name}</h3>

            {entries.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Matière</TableHead>
                    <TableHead>Années</TableHead>
                    <TableHead className="text-right">Classes</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {entries.map((row) => (
                    <SubjectRow
                      key={row.id}
                      row={row}
                      annees={anneesOf.get(row.id) ?? []}
                      flash={justAdded === row.id}
                      onRename={() => setEditing(row)}
                      onDelete={() => deleteSubject(row)}
                    />
                  ))}
                </TableBody>
              </Table>
            )}
            {/* Primaire is a single group where the student is helped with
                everything: one honest matière is enough, offered here in
                one click while it does not exist (renamable afterwards).
                Other levels taken as a block get no suggestion. */}
            {level.name === "Primaire" &&
              !entries.some((row) => row.name === ACCOMPAGNEMENT) && (
                <button
                  type="button"
                  className="border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground mt-2 mb-2 rounded-md border border-dashed px-3 py-1 text-sm"
                  onClick={() =>
                    apiSend("POST", "/api/subjects", {
                      name: ACCOMPAGNEMENT,
                      level_id: level.id,
                    })
                      .then(reload)
                      .catch((err: Error) => setError(err.message))
                  }
                >
                  ＋ {ACCOMPAGNEMENT} (toutes matières)
                </button>
              )}
            {entries.length === 0 && level.name !== "Primaire" && (
              <p className="text-muted-foreground mb-2 text-sm">
                Aucune matière pour ce niveau.
              </p>
            )}

            <AddSubject
              levelId={level.id}
              allNames={[...new Set(rows.map((row) => row.name))]}
              onDone={reload}
              onError={setError}
              onAdded={(id, name) => {
                setJustAdded(id)
                toast(`Matière « ${name} » ajoutée à ${level.name}`)
              }}
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

// The row IS the matière: rename anywhere; delete only where it can
// succeed (no class uses it). Archived leftovers are named, not hidden.
function SubjectRow({
  row,
  annees,
  flash,
  onRename,
  onDelete,
}: {
  row: Row
  /** Where this matière actually lives -- read from its open classes. */
  annees: string[]
  onRename: () => void
  onDelete: () => void
  /** Just created: it pulses once so it can be found. */
  flash?: boolean
}) {
  const taught = annees.length > 0
  const blocked = row.archived_class_count > 0
  return (
    <TableRow className={flash ? "chip-added" : ""}>
      <TableCell className={taught ? "font-medium" : ""}>
        {row.name}
        {!taught && blocked && (
          <span className="text-muted-foreground text-xs">
            {" "}
            · {row.archived_class_count} archivée(s)
          </span>
        )}
      </TableCell>
      {/* Plain text, not chips: the années are an attribute of the matière,
          nothing here is clickable, and a sentence reads faster than a row
          of look-alike boxes. */}
      <TableCell className="text-muted-foreground">
        {taught ? annees.join(", ") : "Pas encore de classe"}
      </TableCell>
      <TableCell className="text-right">{row.class_count}</TableCell>
      <TableCell className="text-right">
        <span className="inline-flex items-center justify-end gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-foreground h-7 w-7 p-0"
            title="Renommer"
            onClick={onRename}
          >
            <Pencil className="size-4" />
          </Button>
          {/* The bin is ALWAYS there -- otherwise one thinks it has been lost.
              It is simply disabled while the matière is taught, with the
              reason on hover. */}
          {taught ? (
            <span
              className="text-muted-foreground inline-flex h-7 w-7 cursor-not-allowed items-center justify-center opacity-30"
              title={`Enseignée dans ${row.class_count} classe(s) — gérez-les d'abord pour pouvoir la supprimer`}
            >
              <Trash2 className="size-4" />
            </span>
          ) : (
            <ConfirmButton
              variant="ghost"
              size="sm"
              className="text-muted-foreground hover:text-destructive h-7 w-7 p-0"
              title={
                blocked
                  ? "Ses classes archivées sans historique partiront avec elle ;" +
                    " un historique d'inscriptions la garde consultable"
                  : "Supprimer cette matière"
              }
              confirmLabel={`Supprimer ${row.name} ?`}
              description="Définitif — ses compétences et ses classes archivées jamais utilisées disparaissent aussi. Refusé si un historique d'inscriptions existe."
              onConfirm={onDelete}
            >
              <Trash2 className="size-4" />
            </ConfirmButton>
          )}
        </span>
      </TableCell>
    </TableRow>
  )
}

function AddSubject({
  levelId,
  allNames,
  onDone,
  onError,
  onAdded,
}: {
  levelId: number
  allNames: string[]
  onDone: () => void
  onError: (message: string) => void
  onAdded: (id: number, name: string) => void
}) {
  const [draft, setDraft] = useState("")
  const field = useRef<HTMLInputElement>(null)

  const submit = () => {
    const name = draft.trim()
    if (!name) return
    apiSend<{ id: number }>("POST", "/api/subjects", { name, level_id: levelId })
      .then(({ id }) => {
        setDraft("")
        // The field keeps focus: three are added in a row without
        // reaching for the mouse.
        field.current?.focus()
        onAdded(id, name)
        onDone()
      })
      .catch((err: Error) => onError(err.message))
  }

  return (
    <div className="mt-3 flex items-center gap-2">
      <Input
        ref={field}
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
      <Button size="sm" onClick={submit} disabled={!draft.trim()}>
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
  const [note, setNote] = useAlert()
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
        <Notice alert={note} />
        <DialogFooter>
          <Button onClick={submit} disabled={busy || !name.trim()}>
            {busy ? "…" : "Enregistrer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
