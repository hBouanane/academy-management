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

type Row = Subject & { class_count: number; archived_class_count: number }

/** La matière unique du Primaire : un seul groupe, aidé sur tout. */
const ACCOMPAGNEMENT = "Accompagnement complet"

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
    return { level, entries, lines: anneeLines(level, entries) }
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

      <Notice message={error} />

      {sections.map(({ level, entries, lines }) => {
        const taught = new Set(
          lines.flatMap((line) => line.subjects.map((row) => row.id)),
        )
        const idle = entries.filter((row) => !taught.has(row.id))
        return (
          <div key={level.id} className="surface-card p-5">
            <h3 className="mb-3 font-medium">{level.name}</h3>

            {lines.length > 0 && (
              <div className="mb-2 space-y-1.5">
                {lines.map((line) => (
                  <div
                    key={line.label}
                    className="flex flex-wrap items-baseline gap-1.5 text-sm"
                  >
                    <span className="text-muted-foreground w-44 shrink-0">
                      {line.label}
                    </span>
                    <span className="flex flex-wrap gap-1">
                      {line.subjects.map((row) => (
                        <SubjectChip
                          key={row.id}
                          row={row}
                          taught
                          onRename={() => setEditing(row)}
                          onDelete={() => deleteSubject(row)}
                        />
                      ))}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {idle.length > 0 && (
              <div className="mb-2 flex flex-wrap items-baseline gap-1.5 text-sm">
                <span className="text-muted-foreground w-44 shrink-0">
                  Pas encore de classe
                </span>
                <span className="flex flex-wrap gap-1">
                  {idle.map((row) => (
                    <SubjectChip
                      key={row.id}
                      row={row}
                      taught={false}
                      onRename={() => setEditing(row)}
                      onDelete={() => deleteSubject(row)}
                    />
                  ))}
                </span>
              </div>
            )}
            {/* Le Primaire est un seul groupe où l'élève est aidé sur tout :
                une matière honnête suffit, proposée ici en un clic tant
                qu'elle n'existe pas (renommable ensuite). Les autres niveaux
                en bloc, eux, ne reçoivent aucune suggestion. */}
            {level.name === "Primaire" &&
              !entries.some((row) => row.name === ACCOMPAGNEMENT) && (
                <button
                  type="button"
                  className="border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground mb-2 rounded-full border border-dashed px-3 py-1 text-sm"
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

// The chip IS the matière: rename anywhere; delete only where it can
// succeed (no class uses it). Archived leftovers are named, not hidden.
function SubjectChip({
  row,
  taught,
  onRename,
  onDelete,
}: {
  row: Row
  taught: boolean
  onRename: () => void
  onDelete: () => void
}) {
  const blocked = row.archived_class_count > 0
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${
        taught
          ? "bg-secondary text-secondary-foreground"
          : "border-border text-muted-foreground border border-dashed"
      }`}
    >
      {row.name}
      {!taught && blocked && (
        <span className="opacity-70">
          · {row.archived_class_count} archivée(s)
        </span>
      )}
      <button
        type="button"
        className="hover:text-foreground opacity-60 hover:opacity-100"
        title="Renommer"
        onClick={onRename}
      >
        <Pencil className="size-3" />
      </button>
      {!taught && (
        <ConfirmButton
          variant="ghost"
          className="text-muted-foreground hover:text-destructive h-4 w-4 rounded-full p-0 opacity-60 hover:bg-transparent hover:opacity-100"
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
          <Trash2 className="size-3" />
        </ConfirmButton>
      )}
    </span>
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
