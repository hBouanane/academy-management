// Classes are the match between a teachable slot (niveau → année → parcours →
// matière) and a capable professor. One wizard creates everything in a single
// flow — matière and professeur can be created inline, no page hopping.

import { useCallback, useEffect, useState } from "react"
import {
  Archive,
  ArchiveRestore,
  Copy,
  FileText,
  Pencil,
  UserRoundPen,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
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
import { TeacherProfile } from "@/components/TeacherProfile"
import { apiGet, apiSend } from "@/lib/api"
import type { Capability, ClassRow, Level, Subject, Teacher } from "@/lib/api"
import {
  hasFiliere,
  parcoursOptions,
  segmentLabel,
  teachingAnnees,
} from "@/lib/levels"

const todayIso = () => {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  return `${now.getFullYear()}-${month}-${String(now.getDate()).padStart(2, "0")}`
}

type Props = { month: string; setMonth: (month: string) => void }

export function Classes({ month, setMonth }: Props) {
  const [rows, setRows] = useState<ClassRow[]>([])
  const [levels, setLevels] = useState<Level[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [capabilities, setCapabilities] = useState<Capability[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [replaceTarget, setReplaceTarget] = useState<ClassRow | null>(null)
  const [duplicateTarget, setDuplicateTarget] = useState<ClassRow | null>(null)
  const [editTarget, setEditTarget] = useState<ClassRow | null>(null)
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

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Classes</h2>
          <p className="text-muted-foreground text-sm">
            Une classe = un créneau (niveau, année, matière) confié à un
            professeur — tout se crée ici, en une fois
          </p>
        </div>
        <div className="flex items-center gap-2">
          <MonthNav month={month} setMonth={setMonth} />
          <Button onClick={() => setWizardOpen(true)}>Nouvelle classe</Button>
        </div>
      </header>

      <Notice message={error} />

      <div className="surface-card p-5">
        <label className="text-muted-foreground mb-4 flex items-center gap-2 text-sm">
          <Checkbox
            checked={showArchived}
            onCheckedChange={(checked) => setShowArchived(checked === true)}
          />
          Afficher les classes archivées
        </label>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Matière</TableHead>
              <TableHead>Segment</TableHead>
              <TableHead>Professeur</TableHead>
              <TableHead>Inscrits ({month})</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow
                key={row.id}
                className="stagger-row"
                style={{ animationDelay: `${index * 40}ms` }}
              >
                <TableCell className="font-medium">
                  {row.subject_name}
                  <Badge variant="outline" className="ml-2">
                    Groupe {row.name}
                  </Badge>
                  {!row.is_active && (
                    <Badge variant="outline" className="ml-1">
                      Archivée
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {segmentLabel(row)}
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
                  <Button size="sm" variant="ghost" asChild title="Liste d'absence (Word)">
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
                    title="Dédoubler — créer le groupe suivant"
                    onClick={() => setDuplicateTarget(row)}
                  >
                    <Copy className="size-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Modifier"
                    onClick={() => setEditTarget(row)}
                  >
                    <Pencil className="size-4" />
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
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-muted-foreground text-center">
                  Aucune classe — créez la première.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <ClassWizard
        open={wizardOpen}
        onOpenChange={setWizardOpen}
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

      {editTarget && (
        <EditClassDialog
          target={editTarget}
          teachers={teachers}
          onClose={() => setEditTarget(null)}
          onDone={() => {
            setEditTarget(null)
            reload()
          }}
        />
      )}

      <TeacherProfile
        teacherId={profileTeacher}
        month={month}
        onClose={() => setProfileTeacher(null)}
      />
    </div>
  )
}

function ClassWizard({
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
  const [levelId, setLevelId] = useState("")
  const [annee, setAnnee] = useState("")
  const [parcours, setParcours] = useState("")
  const [filiere, setFiliere] = useState("")
  const [subjectId, setSubjectId] = useState("")
  const [newSubject, setNewSubject] = useState("")
  const [teacherId, setTeacherId] = useState("")
  const [showAllTeachers, setShowAllTeachers] = useState(false)
  const [newTeacherName, setNewTeacherName] = useState("")
  const [newTeacherPhone, setNewTeacherPhone] = useState("")
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setLevelId("")
    setAnnee("")
    setParcours("")
    setFiliere("")
    setSubjectId("")
    setNewSubject("")
    setTeacherId("")
    setShowAllTeachers(false)
    setNewTeacherName("")
    setNewTeacherPhone("")
    setNote(null)
    setBusy(false)
  }, [open])

  const levelName = levels.find((level) => String(level.id) === levelId)?.name ?? ""
  const annees = teachingAnnees(levelName)
  const parcoursChoices = parcoursOptions(levelName, annee)

  // A prof is proposed when a capability matches the slot (NULL = wildcard).
  const capableIds = new Set(
    capabilities
      .filter(
        (capability) =>
          String(capability.level_id) === levelId &&
          (subjectId === "" || String(capability.subject_id) === subjectId) &&
          (capability.annee === null ||
            annee === "" ||
            String(capability.annee) === annee) &&
          (capability.parcours === null ||
            parcours === "" ||
            capability.parcours === parcours),
      )
      .map((capability) => capability.teacher_id),
  )
  const proposedTeachers = showAllTeachers
    ? teachers
    : teachers.filter((teacher) => capableIds.has(teacher.id))

  const submit = async () => {
    if (!levelId) return setNote("Choisissez un niveau.")
    if (annees.length > 0 && !annee) return setNote("Choisissez l'année.")
    if (parcoursChoices.length > 0 && !parcours)
      return setNote("Choisissez le parcours (Normal ou Râ'ida).")
    if (!subjectId && !newSubject.trim())
      return setNote("Choisissez une matière ou saisissez-en une nouvelle.")
    if (!teacherId && !newTeacherName.trim())
      return setNote("Choisissez un professeur ou créez-en un.")
    setNote(null)
    setBusy(true)
    try {
      const subject = newSubject.trim()
        ? (
            await apiSend<{ id: number }>("POST", "/api/subjects", {
              name: newSubject.trim(),
            })
          ).id
        : Number(subjectId)
      const teacher = newTeacherName.trim()
        ? (
            await apiSend<{ id: number }>("POST", "/api/teachers", {
              name: newTeacherName.trim(),
              phone: newTeacherPhone.replace(/[\s.-]/g, "") || null,
            })
          ).id
        : Number(teacherId)
      await apiSend("POST", "/api/classes", {
        level_id: Number(levelId),
        subject_id: subject,
        teacher_id: teacher,
        annee: annee ? Number(annee) : null,
        parcours: parcours || null,
        filiere: hasFiliere(levelName, annee) ? filiere.trim() || null : null,
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
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Nouvelle classe</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <div className="min-w-32 flex-1 space-y-2">
              <Label>Niveau</Label>
              <Select
                value={levelId}
                onValueChange={(value) => {
                  setLevelId(value)
                  setAnnee("")
                  setParcours("")
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Niveau" />
                </SelectTrigger>
                <SelectContent>
                  {levels.map((level) => (
                    <SelectItem key={level.id} value={String(level.id)}>
                      {level.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {annees.length > 0 && (
              <div className="min-w-32 flex-1 space-y-2">
                <Label>Année</Label>
                <Select
                  value={annee}
                  onValueChange={(value) => {
                    setAnnee(value)
                    setParcours("")
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Année" />
                  </SelectTrigger>
                  <SelectContent>
                    {annees.map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {parcoursChoices.length > 0 && (
              <div className="min-w-32 flex-1 space-y-2">
                <Label>Parcours</Label>
                <Select value={parcours} onValueChange={setParcours}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Parcours" />
                  </SelectTrigger>
                  <SelectContent>
                    {parcoursChoices.map((choice) => (
                      <SelectItem key={choice} value={choice}>
                        {choice}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {hasFiliere(levelName, annee) && (
              <div className="min-w-36 flex-1 space-y-2">
                <Label>
                  Filière <span className="text-muted-foreground">(optionnel)</span>
                </Label>
                <Input
                  value={filiere}
                  onChange={(event) => setFiliere(event.target.value)}
                  placeholder="Toutes filières"
                />
              </div>
            )}
          </div>

          <div className="space-y-2">
            <Label>Matière</Label>
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={subjectId}
                onValueChange={(value) => {
                  setSubjectId(value)
                  setNewSubject("")
                }}
              >
                <SelectTrigger className="min-w-40 flex-1">
                  <SelectValue placeholder="Matière existante" />
                </SelectTrigger>
                <SelectContent>
                  {subjects.map((subject) => (
                    <SelectItem key={subject.id} value={String(subject.id)}>
                      {subject.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-muted-foreground text-xs">ou</span>
              <Input
                value={newSubject}
                onChange={(event) => {
                  setNewSubject(event.target.value)
                  if (event.target.value) setSubjectId("")
                }}
                placeholder="Nouvelle matière"
                className="min-w-36 flex-1"
              />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Professeur</Label>
              <label className="text-muted-foreground flex items-center gap-1.5 text-xs">
                <Checkbox
                  checked={showAllTeachers}
                  onCheckedChange={(state) => setShowAllTeachers(state === true)}
                />
                Voir tous les professeurs
              </label>
            </div>
            <Select
              value={teacherId}
              onValueChange={(value) => {
                setTeacherId(value)
                setNewTeacherName("")
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue
                  placeholder={
                    proposedTeachers.length
                      ? "Professeurs compétents pour ce créneau"
                      : "Aucun professeur compétent — voir tous, ou créer"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {proposedTeachers.map((teacher) => (
                  <SelectItem key={teacher.id} value={String(teacher.id)}>
                    {teacher.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground text-xs">ou nouveau :</span>
              <Input
                value={newTeacherName}
                onChange={(event) => {
                  setNewTeacherName(event.target.value)
                  if (event.target.value) setTeacherId("")
                }}
                placeholder="Nom du professeur"
                className="min-w-36 flex-1"
              />
              <Input
                value={newTeacherPhone}
                onChange={(event) => setNewTeacherPhone(event.target.value)}
                placeholder="Téléphone (optionnel)"
                className="w-44"
              />
            </div>
            <p className="text-muted-foreground text-xs">
              La compétence du professeur pour ce créneau s'enregistre toute
              seule.
            </p>
          </div>

          <Notice message={note} />
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : "Créer la classe"}
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
            Remplacer {target.teacher_name} — {target.subject_name} · Groupe{" "}
            {target.name}
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
          <DialogTitle>
            Dédoubler {target.subject_name} · Groupe {target.name}
          </DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          Trop d'étudiants ? Un nouveau groupe du même créneau est créé (groupe
          suivant), avec le même professeur ou un autre.
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

function EditClassDialog({
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
  const [name, setName] = useState(target.name)
  const [teacherId, setTeacherId] = useState(String(target.teacher_id))
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const submit = () => {
    setBusy(true)
    apiSend("PATCH", `/api/classes/${target.id}`, {
      name,
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
          <DialogTitle>
            Modifier {target.subject_name} · Groupe {target.name}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Nom du groupe</Label>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Professeur</Label>
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
            <p className="text-muted-foreground text-xs">
              Ici c'est une CORRECTION (mauvais nom saisi) : le nouveau nom vaut
              pour tout le passé. Pour un vrai changement de professeur, utilisez
              « Remplacer » — l'argent suivra les dates.
            </p>
          </div>
          <Notice message={note} />
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : "Enregistrer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
