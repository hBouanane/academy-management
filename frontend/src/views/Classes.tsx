// The read-mostly overview of open classes, one table per niveau. Creation
// happens through THE tree (pick one slot) then a capable professor — and
// most of the time not even here: profs open their classes from their
// profile. No « Groupe A » : a class alone needs no label; siblings are
// told apart by their professor.

import { useCallback, useEffect, useState } from "react"
import {
  Archive,
  ArchiveRestore,
  Copy,
  FileText,
  UserRoundPen,
} from "lucide-react"
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ConfirmButton } from "@/components/Confirm"
import { MonthNav } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { ProgramTree } from "@/components/ProgramTree"
import type { TreeSlot } from "@/components/ProgramTree"
import { TeacherProfile } from "@/components/TeacherProfile"
import { apiGet, apiSend } from "@/lib/api"
import type { Capability, ClassRow, Level, Subject, Teacher } from "@/lib/api"
import { anneeLabel } from "@/lib/levels"

const todayIso = () => {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  return `${now.getFullYear()}-${month}-${String(now.getDate()).padStart(2, "0")}`
}

const sameSlot = (a: ClassRow, b: ClassRow) =>
  a.level_id === b.level_id &&
  a.subject_id === b.subject_id &&
  a.annee === b.annee &&
  a.parcours === b.parcours &&
  a.filiere === b.filiere

type Props = { month: string; setMonth: (month: string) => void }

export function Classes({ month, setMonth }: Props) {
  const [rows, setRows] = useState<ClassRow[]>([])
  const [levels, setLevels] = useState<Level[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [capabilities, setCapabilities] = useState<Capability[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [replaceTarget, setReplaceTarget] = useState<ClassRow | null>(null)
  const [duplicateTarget, setDuplicateTarget] = useState<ClassRow | null>(null)
  const [profileTeacher, setProfileTeacher] = useState<number | null>(null)

  const reload = useCallback(() => {
    apiGet<ClassRow[]>(
      `/api/classes?include_inactive=${showArchived}&month=${month}`,
    )
      .then(setRows)
      .catch((err: Error) => setError(err.message))
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
    apiGet<Subject[]>("/api/subjects").then(setSubjects).catch(() => {})
    apiGet<Teacher[]>("/api/teachers").then(setTeachers).catch(() => {})
    apiGet<Capability[]>("/api/capabilities").then(setCapabilities).catch(() => {})
  }, [month, showArchived])
  useEffect(reload, [reload])

  const setActive = (row: ClassRow, active: boolean) =>
    apiSend("PATCH", `/api/classes/${row.id}`, { is_active: active })
      .then(reload)
      .catch((err: Error) => setError(err.message))

  const byLevel = levels
    .map((level) => ({
      level,
      classes: rows.filter((row) => row.level_id === level.id),
    }))
    .filter((group) => group.classes.length > 0)

  const rowLabel = (row: ClassRow) => {
    const siblings = rows.filter(
      (other) => other.is_active === 1 && sameSlot(other, row),
    )
    if (siblings.length <= 1) return ""
    const sameTeacher = siblings.filter(
      (other) => other.teacher_name === row.teacher_name,
    )
    if (sameTeacher.length <= 1) return ` · groupe de ${row.teacher_name}`
    const position = sameTeacher.findIndex((other) => other.id === row.id) + 1
    return ` · groupe de ${row.teacher_name} №${position}`
  }

  const segment = (row: ClassRow) => {
    const parts: string[] = []
    const annee = anneeLabel(row.level_name, row.annee)
    if (annee) parts.push(annee)
    if (row.parcours) parts.push(row.parcours)
    if (row.annee !== null && !row.parcours && row.level_name === "Collège" && row.annee === 3)
      parts.push("classe commune")
    if (row.filiere) parts.push(row.filiere)
    return parts.join(" · ") || "—"
  }

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Classes</h2>
          <p className="text-muted-foreground text-sm">
            Les classes ouvertes — elles naissent surtout depuis le profil des
            professeurs
          </p>
        </div>
        <div className="flex items-center gap-2">
          <MonthNav month={month} setMonth={setMonth} />
          <Button onClick={() => setCreateOpen(true)}>Nouvelle classe</Button>
        </div>
      </header>

      <Notice message={error} />

      <label className="text-muted-foreground flex items-center gap-2 text-sm">
        <Checkbox
          checked={showArchived}
          onCheckedChange={(checked) => setShowArchived(checked === true)}
        />
        Afficher les classes archivées
      </label>

      {byLevel.length === 0 && (
        <div className="surface-card p-8 text-center">
          <p className="text-muted-foreground text-sm">
            Aucune classe. Créez un professeur, cochez son arbre, puis « ouvrir
            la classe » depuis son profil — ou utilisez « Nouvelle classe ».
          </p>
        </div>
      )}

      {byLevel.map(({ level, classes }) => (
        <div key={level.id} className="surface-card p-5">
          <h3 className="mb-3 font-medium">{level.name}</h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Matière</TableHead>
                <TableHead>Année · Parcours</TableHead>
                <TableHead>Professeur</TableHead>
                <TableHead>Inscrits ({month})</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {classes.map((row, index) => (
                <TableRow
                  key={row.id}
                  className="stagger-row"
                  style={{ animationDelay: `${index * 40}ms` }}
                >
                  <TableCell className="font-medium">
                    {row.subject_name}
                    <span className="text-muted-foreground text-xs">
                      {rowLabel(row)}
                    </span>
                    {!row.is_active && (
                      <span className="text-muted-foreground text-xs">
                        {" "}
                        (archivée)
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {segment(row)}
                  </TableCell>
                  <TableCell>
                    <button
                      className="underline-offset-4 hover:underline"
                      onClick={() => setProfileTeacher(row.teacher_id)}
                      title="Profil du professeur"
                    >
                      {row.teacher_name}
                    </button>
                  </TableCell>
                  <TableCell>{row.enrolled_count ?? 0}</TableCell>
                  <TableCell className="space-x-1 text-right whitespace-nowrap">
                    <Button
                      size="sm"
                      variant="ghost"
                      asChild
                      title="Liste d'absence (Word)"
                    >
                      <a
                        href={`/api/classes/${row.id}/absence.docx?month=${month}`}
                        download
                      >
                        <FileText className="size-4" />
                      </a>
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      title="Remplacer le professeur (daté — l'argent suit les jours)"
                      onClick={() => setReplaceTarget(row)}
                    >
                      <UserRoundPen className="size-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      title="Dédoubler — un deuxième groupe du même créneau"
                      onClick={() => setDuplicateTarget(row)}
                    >
                      <Copy className="size-4" />
                    </Button>
                    <ConfirmButton
                      size="sm"
                      variant="ghost"
                      confirmLabel={
                        row.is_active ? "Archiver cette classe ?" : "Restaurer ?"
                      }
                      description="Réversible — l'historique financier reste intact."
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
        </div>
      ))}

      <NewClassDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        levels={levels}
        subjects={subjects}
        teachers={teachers}
        capabilities={capabilities}
        onDone={reload}
      />

      {replaceTarget && (
        <ReplaceTeacherDialog
          target={replaceTarget}
          teachers={teachers}
          onClose={() => setReplaceTarget(null)}
          onDone={() => {
            setReplaceTarget(null)
            reload()
          }}
        />
      )}

      {duplicateTarget && (
        <DuplicateDialog
          target={duplicateTarget}
          teachers={teachers}
          onClose={() => setDuplicateTarget(null)}
          onDone={() => {
            setDuplicateTarget(null)
            reload()
          }}
        />
      )}

      <TeacherProfile
        teacherId={profileTeacher}
        month={month}
        onClose={() => setProfileTeacher(null)}
        onChanged={reload}
      />
    </div>
  )
}

function NewClassDialog({
  open,
  onOpenChange,
  levels,
  subjects,
  teachers,
  capabilities,
  onDone,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  levels: Level[]
  subjects: Subject[]
  teachers: Teacher[]
  capabilities: Capability[]
  onDone: () => void
}) {
  const [picked, setPicked] = useState<TreeSlot | null>(null)
  const [teacherId, setTeacherId] = useState<number | null>(null)
  const [draft, setDraft] = useState("")
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setPicked(null)
    setTeacherId(null)
    setDraft("")
    setNote(null)
    setBusy(false)
  }, [open])

  // Capable = a capability matching the picked slot (NULL acts as wildcard).
  const capable = picked
    ? teachers.filter((teacher) =>
        capabilities.some(
          (capability) =>
            capability.teacher_id === teacher.id &&
            capability.level_id === picked.level_id &&
            capability.subject_id === picked.subject_id &&
            (capability.annee === null ||
              picked.annee === null ||
              capability.annee === picked.annee) &&
            (capability.parcours === null ||
              picked.parcours === null ||
              capability.parcours === picked.parcours),
        ),
      )
    : []

  const submit = async () => {
    if (!picked) {
      setNote("Choisissez un créneau dans l'arbre (une matière).")
      return
    }
    let chosen = teacherId
    const typed = draft.trim()
    if (chosen === null && !typed) {
      setNote("Choisissez un professeur, ou tapez son nom (nouveau ou existant).")
      return
    }
    setNote(null)
    setBusy(true)
    try {
      if (chosen === null) {
        const existing = teachers.find(
          (teacher) => teacher.name.toLowerCase() === typed.toLowerCase(),
        )
        chosen = existing
          ? existing.id
          : (
              await apiSend<{ id: number }>("POST", "/api/teachers", {
                name: typed,
              })
            ).id
      }
      await apiSend("POST", "/api/classes", {
        level_id: picked.level_id,
        subject_id: picked.subject_id,
        teacher_id: chosen,
        annee: picked.annee,
        parcours: picked.parcours,
      })
      onOpenChange(false)
      onDone()
    } catch (err) {
      setNote((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Nouvelle classe</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
              1 — Choisissez le créneau dans l'arbre
            </p>
            <ProgramTree
              mode="pick"
              levels={levels}
              subjects={subjects}
              picked={picked}
              onPick={setPicked}
              onGrown={onDone}
            />
          </div>

          <div>
            <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
              2 — Le professeur
            </p>
            {picked === null && (
              <p className="text-muted-foreground text-sm">
                Les professeurs compétents apparaîtront ici.
              </p>
            )}
            {picked !== null && (
              <div className="flex flex-wrap items-center gap-1.5">
                {capable.map((teacher) => (
                  <button
                    key={teacher.id}
                    type="button"
                    onClick={() => {
                      setTeacherId(teacher.id)
                      setDraft("")
                    }}
                    className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                      teacherId === teacher.id
                        ? "border-transparent bg-primary text-primary-foreground"
                        : "border-border text-muted-foreground hover:border-foreground/40"
                    }`}
                  >
                    {teacherId === teacher.id ? "✓ " : ""}
                    {teacher.name}
                  </button>
                ))}
                <Input
                  list="all-teachers"
                  value={draft}
                  onChange={(event) => {
                    setDraft(event.target.value)
                    if (event.target.value) setTeacherId(null)
                  }}
                  placeholder="＋ professeur…"
                  className="h-7 w-40 text-xs"
                />
                <datalist id="all-teachers">
                  {teachers.map((teacher) => (
                    <option key={teacher.id} value={teacher.name} />
                  ))}
                </datalist>
              </div>
            )}
            <p className="text-muted-foreground mt-1.5 text-xs">
              Un nom tapé qui n'existe pas crée le professeur ; sa compétence
              pour ce créneau s'enregistre toute seule.
            </p>
          </div>

          <Notice message={note} />
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : "Ouvrir la classe"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ReplaceTeacherDialog({
  target,
  teachers,
  onClose,
  onDone,
}: {
  target: ClassRow
  teachers: Teacher[]
  onClose: () => void
  onDone: () => void
}) {
  const [date, setDate] = useState(todayIso())
  const [successors, setSuccessors] = useState<Set<number>>(new Set())
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = () => {
    if (successors.size === 0) {
      setNote("Choisissez au moins un successeur.")
      return
    }
    setNote(null)
    setBusy(true)
    apiSend("POST", `/api/classes/${target.id}/replace-teacher`, {
      date,
      successor_ids: [...successors],
    })
      .then(onDone)
      .catch((err: Error) => {
        setNote(err.message)
        setBusy(false)
      })
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            Remplacer {target.teacher_name} — {target.subject_name}
          </DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          {target.teacher_name} est payé jusqu'à la veille de cette date, les
          successeurs à partir de celle-ci — même quand un vieux mois impayé se
          règle plus tard. L'ancien professeur peut ensuite être archivé sans
          rien perdre.
        </p>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Date de prise de fonction</Label>
            <Input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Successeur(s) — un ou plusieurs</Label>
            <div className="border-border max-h-44 space-y-1.5 overflow-y-auto rounded-lg border p-3">
              {teachers
                .filter((teacher) => teacher.id !== target.teacher_id)
                .map((teacher) => (
                  <label
                    key={teacher.id}
                    className="flex items-center gap-2 text-sm"
                  >
                    <Checkbox
                      checked={successors.has(teacher.id)}
                      onCheckedChange={(state) =>
                        setSuccessors((current) => {
                          const next = new Set(current)
                          if (state === true) next.add(teacher.id)
                          else next.delete(teacher.id)
                          return next
                        })
                      }
                    />
                    {teacher.name}
                  </label>
                ))}
            </div>
          </div>
          <Notice message={note} />
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : "Remplacer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DuplicateDialog({
  target,
  teachers,
  onClose,
  onDone,
}: {
  target: ClassRow
  teachers: Teacher[]
  onClose: () => void
  onDone: () => void
}) {
  const [teacherId, setTeacherId] = useState(String(target.teacher_id))
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const submit = () => {
    setBusy(true)
    apiSend("POST", `/api/classes/${target.id}/duplicate`, {
      teacher_id: Number(teacherId),
    })
      .then(onDone)
      .catch((err: Error) => {
        setNote(err.message)
        setBusy(false)
      })
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Dédoubler {target.subject_name}</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          Trop d'étudiants ? Un deuxième groupe du même créneau est créé — les
          deux se distinguent par leur professeur.
        </p>
        <div className="space-y-2">
          <Label>Professeur du nouveau groupe</Label>
          <Select value={teacherId} onValueChange={setTeacherId}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {teachers.map((teacher) => (
                <SelectItem key={teacher.id} value={String(teacher.id)}>
                  {teacher.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Notice message={note} />
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : "Créer le groupe"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
