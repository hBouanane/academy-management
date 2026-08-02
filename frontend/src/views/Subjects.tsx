// Matières grouped by their niveau — one section per niveau, each with its
// own single add-field. A matière typed here belongs to this niveau only.

import { useCallback, useEffect, useState } from "react"
import { Archive, ArchiveRestore, Pencil } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ConfirmButton } from "@/components/Confirm"
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import type { ClassRow, Level, Subject } from "@/lib/api"
import { anneeLabel } from "@/lib/levels"

type Row = Subject & { class_count: number; is_active: number }

export function Subjects() {
  const [levels, setLevels] = useState<Level[]>([])
  const [rows, setRows] = useState<Row[]>([])
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Row | null>(null)

  const reload = useCallback(() => {
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
    apiGet<ClassRow[]>("/api/classes").then(setClasses).catch(() => {})
    apiGet<Row[]>(`/api/subjects?include_inactive=${showArchived}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message))
  }, [showArchived])
  useEffect(reload, [reload])

  // Where a matière is actually taught: année/parcours/filière of its classes.
  const segmentsOf = (subjectId: number) =>
    classes
      .filter((row) => row.subject_id === subjectId && row.is_active === 1)
      .map((row) => {
        const parts: string[] = []
        const annee = anneeLabel(row.level_name, row.annee)
        if (annee) parts.push(annee)
        if (row.parcours) parts.push(row.parcours)
        if (row.filiere) parts.push(row.filiere)
        return parts.join(" · ") || "Bloc unique"
      })

  const setActive = (row: Row, active: boolean) =>
    apiSend("PATCH", `/api/subjects/${row.id}`, { is_active: active })
      .then(reload)
      .catch((err: Error) => setError(err.message))

  const legacy = rows.filter((row) => row.level_id === null)
  const sections: { title: string; levelId: number | null; entries: Row[] }[] = [
    ...levels.map((level) => ({
      title: level.name,
      levelId: level.id as number | null,
      entries: rows.filter((row) => row.level_id === level.id),
    })),
    ...(legacy.length > 0
      ? [
          {
            title: "Tous niveaux (anciennes)",
            levelId: null,
            entries: legacy,
          },
        ]
      : []),
  ]

  return (
    <div className="view-enter space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Matières</h2>
        <p className="text-muted-foreground text-sm">
          Chaque matière appartient à son niveau — le même nom ailleurs est une
          entrée à part
        </p>
      </header>

      <Notice message={error} />

      <label className="text-muted-foreground flex items-center gap-2 text-sm">
        <Checkbox
          checked={showArchived}
          onCheckedChange={(checked) => setShowArchived(checked === true)}
        />
        Afficher les matières archivées
      </label>

      {sections.map((section) => (
        <div key={section.title} className="surface-card p-5">
          <h3 className="mb-3 font-medium">{section.title}</h3>
          {section.entries.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nom</TableHead>
                  <TableHead>Enseignée en</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {section.entries.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="font-medium">
                      {row.name}
                      {!row.is_active && (
                        <span className="text-muted-foreground text-xs">
                          {" "}
                          (archivée)
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex max-w-96 flex-wrap gap-1">
                        {segmentsOf(row.id).map((segment, index) => (
                          <span
                            key={index}
                            className="bg-secondary text-secondary-foreground rounded-full px-2 py-0.5 text-xs"
                          >
                            {segment}
                          </span>
                        ))}
                        {segmentsOf(row.id).length === 0 && (
                          <span className="text-muted-foreground text-xs">
                            Aucune classe
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="space-x-1 text-right whitespace-nowrap">
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
                        confirmLabel={
                          row.is_active ? "Archiver cette matière ?" : "Restaurer ?"
                        }
                        description="Réversible — les classes et l'historique restent."
                        onConfirm={() => setActive(row, !row.is_active)}
                      >
                        {row.is_active ? (
                          <Archive className="size-4" />
                        ) : (
                          <ArchiveRestore className="size-4" />
                        )}
                      </ConfirmButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {section.entries.length === 0 && (
            <p className="text-muted-foreground mb-2 text-sm">
              Aucune matière pour ce niveau.
            </p>
          )}
          {section.levelId !== null && (
            <AddSubject
              levelId={section.levelId}
              allNames={[...new Set(rows.map((row) => row.name))]}
              onDone={reload}
              onError={setError}
            />
          )}
        </div>
      ))}

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
