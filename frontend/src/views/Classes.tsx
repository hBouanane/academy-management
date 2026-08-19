// The read-mostly overview of open classes, one table per niveau. Creation
// happens through THE tree (pick one slot) then a capable professor — and
// most of the time not even here: profs open their classes from their
// profile. No « Groupe A » : a class alone needs no label; siblings are
// told apart by their professor.

import { useCallback, useEffect, useRef, useState } from "react"
import {
  Archive,
  ArchiveRestore,
  Copy,
  FileText,
  Trash2,
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
import { ArchiveClassDialog } from "@/components/ArchiveClassDialog"
import { ClassProfile } from "@/components/ClassProfile"
import { ConfirmButton } from "@/components/Confirm"
import { StudentProfile } from "@/components/StudentProfile"
import { MonthNav, monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { FileDocument } from "@/components/FileDocument"
import { subjectsOfLevel } from "@/components/ProgramTree"
import { TeacherProfile } from "@/components/TeacherProfile"
import { useAlert } from "@/lib/alert"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"
import type { Capability, ClassRow, Level, Subject, Teacher } from "@/lib/api"
import {
  anneeLabel,
  filiereDefaults,
  hasFiliere,
  parcoursOptions,
  teachingAnnees,
} from "@/lib/levels"

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
  const [filieres, setFilieres] = useState<string[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useAlert()
  const [createOpen, setCreateOpen] = useState(false)
  const [replaceTarget, setReplaceTarget] = useState<ClassRow | null>(null)
  const [duplicateTarget, setDuplicateTarget] = useState<ClassRow | null>(null)
  const [archiveTarget, setArchiveTarget] = useState<ClassRow | null>(null)
  const [profileTeacher, setProfileTeacher] = useState<number | null>(null)
  const [profileClass, setProfileClass] = useState<number | null>(null)
  const [profileStudent, setProfileStudent] = useState<number | null>(null)

  const reload = useCallback(() => {
    setError(null)
    apiGet<ClassRow[]>(
      `/api/classes?include_inactive=${showArchived}&month=${month}`,
    )
      .then(setRows)
      .catch((err: Error) => setError(err.message))
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
    apiGet<Subject[]>("/api/subjects").then(setSubjects).catch(() => {})
    apiGet<Teacher[]>("/api/teachers").then(setTeachers).catch(() => {})
    apiGet<Capability[]>("/api/capabilities").then(setCapabilities).catch(() => {})
    apiGet<string[]>("/api/filieres").then(setFilieres).catch(() => {})
  }, [month, showArchived, setError])
  useEffect(reload, [reload])

  const restore = (row: ClassRow) =>
    apiSend("PATCH", `/api/classes/${row.id}`, { is_active: true })
      .then(reload)
      .catch((err: Error) => setError(err.message))

  const deleteClass = (row: ClassRow) =>
    apiSend("DELETE", `/api/classes/${row.id}`)
      .then(reload)
      .catch((err: Error) => setError(err.message))

  const byLevel = levels
    .map((level) => ({
      level,
      classes: rows.filter((row) => row.level_id === level.id),
    }))
    .filter((group) => group.classes.length > 0)

  // The owner's brain is année-first: inside each niveau, one sub-section
  // per année (3ème collège forks per parcours; Bac rows carry la filière).
  const sectionsOf = (level: Level, classes: ClassRow[]) => {
    if (level.teaching_annees === 0)
      return [{ key: "bloc", label: null as string | null, entries: classes }]
    const keyed = new Map<string, { label: string | null; entries: ClassRow[] }>()
    for (const row of classes) {
      const base = anneeLabel(level.name, row.annee) ?? "Sans année"
      const fork = row.parcours
        ? ` — ${row.parcours}`
        : row.level_name === "Collège" && row.annee === 3
          ? " — Commune"
          : ""
      const label = `${base}${fork}`
      const key = `${row.annee ?? 0}|${row.parcours ?? ""}`
      if (!keyed.has(key)) keyed.set(key, { label, entries: [] })
      keyed.get(key)!.entries.push(row)
    }
    return [...keyed.entries()]
      .sort(([a], [b]) => a.localeCompare(b, "fr", { numeric: true }))
      .map(([key, section]) => ({ key, ...section }))
  }

  const rowLabel = (row: ClassRow) => {
    const siblings = rows.filter(
      (other) => other.is_active === 1 && sameSlot(other, row),
    )
    if (siblings.length <= 1) return ""
    if (row.teacher_name === null) return " · groupe sans professeur"
    const sameTeacher = siblings.filter(
      (other) => other.teacher_name === row.teacher_name,
    )
    if (sameTeacher.length <= 1) return ` · groupe de ${row.teacher_name}`
    const position = sameTeacher.findIndex((other) => other.id === row.id) + 1
    return ` · groupe de ${row.teacher_name} №${position}`
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

      <Notice alert={error} />

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
          <div className="space-y-4">
            {sectionsOf(level, classes).map((section) => (
              <div key={section.key}>
                {section.label && (
                  <h4 className="text-muted-foreground mb-1.5 text-sm font-medium">
                    {section.label}
                  </h4>
                )}
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Matière</TableHead>
                      <TableHead>Filière</TableHead>
                      <TableHead>Professeur</TableHead>
                      <TableHead className="capitalize">
                        Inscrits — {monthLabel(month)}
                      </TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {section.entries.map((row, index) => (
                      <TableRow
                        key={row.id}
                        className="stagger-row cursor-pointer"
                        style={{ animationDelay: `${index * 40}ms` }}
                        title="Ouvrir la fiche de la classe"
                        onClick={(event) => {
                          const target = event.target as HTMLElement
                          if (!event.currentTarget.contains(target)) return
                          if (target.closest("button, a")) return
                          setProfileClass(row.id)
                        }}
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
                          {row.filiere ?? "—"}
                        </TableCell>
                        <TableCell>
                          {row.teacher_id === null ? (
                            <button
                              className="bg-destructive/10 text-destructive rounded-full px-2.5 py-0.5 text-xs font-medium"
                              title="Sans professeur — cliquez pour en nommer un"
                              onClick={() => setReplaceTarget(row)}
                            >
                              Sans professeur — à pourvoir
                            </button>
                          ) : (
                            <button
                              className="underline-offset-4 hover:underline"
                              onClick={() => setProfileTeacher(row.teacher_id)}
                              title="Profil du professeur"
                            >
                              {row.teacher_name}
                            </button>
                          )}
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
                          <FileDocument
                            kind="absence"
                            month={month}
                            refId={row.id}
                            ready
                            className="h-8 border-0 px-2 shadow-none"
                          >
                            {""}
                          </FileDocument>
                          <Button
                            size="sm"
                            variant="ghost"
                            title={
                              row.teacher_id === null
                                ? "Nommer un professeur (daté)"
                                : "Remplacer le professeur (daté — l'argent suit les jours)"
                            }
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
                          {row.is_active ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              title="Archiver — désinscrit les étudiants du mois, remboursements au choix"
                              onClick={() => setArchiveTarget(row)}
                            >
                              <Archive className="size-4" />
                            </Button>
                          ) : (
                            <ConfirmButton
                              size="sm"
                              variant="ghost"
                              title="Restaurer"
                              confirmLabel="Restaurer cette classe ?"
                              description="Elle redevient active — les étudiants ne sont pas réinscrits automatiquement."
                              onConfirm={() => restore(row)}
                            >
                              <ArchiveRestore className="size-4" />
                            </ConfirmButton>
                          )}
                          <ConfirmButton
                            size="sm"
                            variant="ghost"
                            title="Supprimer (uniquement si personne n'y a jamais été inscrit)"
                            confirmLabel="Supprimer cette classe ?"
                            description="Réservé aux classes créées par erreur — refusé dès qu'un étudiant y a été inscrit."
                            onConfirm={() => deleteClass(row)}
                          >
                            <Trash2 className="size-4" />
                          </ConfirmButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ))}
          </div>
        </div>
      ))}

      <NewClassDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        levels={levels}
        subjects={subjects}
        teachers={teachers}
        capabilities={capabilities}
        knownFilieres={filieres}
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

      {archiveTarget && (
        <ArchiveClassDialog
          target={archiveTarget}
          onClose={() => setArchiveTarget(null)}
          onDone={() => {
            setArchiveTarget(null)
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

      <ClassProfile
        classId={profileClass}
        month={month}
        onClose={() => setProfileClass(null)}
        onShowStudent={setProfileStudent}
      />

      <StudentProfile
        studentId={profileStudent}
        onClose={() => setProfileStudent(null)}
        onChanged={reload}
      />
    </div>
  )
}

const COMMUNE = "__commune__"

function StepChip({
  active,
  onClick,
  children,
  flash = false,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
  /** Vient d'être créée : elle pulse une fois pour se faire trouver. */
  flash?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-sm transition-colors ${
        active
          ? "border-transparent bg-primary text-primary-foreground font-medium"
          : "border-border text-muted-foreground hover:border-foreground/40"
      } ${flash ? "chip-added" : ""}`}
    >
      {children}
    </button>
  )
}

function Step({
  number,
  title,
  children,
}: {
  number: number
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="border-border rounded-xl border p-3">
      <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
        {number} — {title}
      </p>
      {children}
    </div>
  )
}

// One class = one créneau + one matière + one professeur, so the form is a
// cascade: each choice reveals the next step. No tree dump, no double fields.
function NewClassDialog({
  open,
  onOpenChange,
  levels,
  subjects,
  teachers,
  capabilities,
  knownFilieres,
  onDone,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  levels: Level[]
  subjects: Subject[]
  teachers: Teacher[]
  capabilities: Capability[]
  knownFilieres: string[]
  onDone: () => void
}) {
  const [levelId, setLevelId] = useState<number | null>(null)
  const [annee, setAnnee] = useState<number | null>(null)
  const [parcours, setParcours] = useState<string | null>(null) // COMMUNE = mixed
  // Multi-select: ONE CLASS PER SELECTED FILIÈRE is created. Empty selection
  // = one classe commune (all filières together).
  const [filieres, setFilieres] = useState<Set<string>>(new Set())
  const [filiereDraft, setFiliereDraft] = useState("")
  const [subjectId, setSubjectId] = useState<number | null>(null)
  const [subjectDraft, setSubjectDraft] = useState("")
  // La matière créée à l'instant : elle pulse le temps qu'on la repère.
  const [justAdded, setJustAdded] = useState<number | null>(null)
  const subjectInput = useRef<HTMLInputElement>(null)
  const toast = useToast()
  const [teacherId, setTeacherId] = useState<number | null>(null)
  const [teacherDraft, setTeacherDraft] = useState("")
  const [note, setNote] = useAlert()
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setLevelId(null)
    setAnnee(null)
    setParcours(null)
    setFilieres(new Set())
    setFiliereDraft("")
    setSubjectId(null)
    setSubjectDraft("")
    setTeacherId(null)
    setTeacherDraft("")
    setNote(null)
    setBusy(false)
  }, [open, setNote])

  const level = levels.find((entry) => entry.id === levelId)
  const annees = level ? teachingAnnees(level) : []
  const forks =
    level && annee !== null ? parcoursOptions(level.name, String(annee)) : []
  const levelSubjects = level ? subjectsOfLevel(subjects, level.id) : []
  // Bac years: each filière MAY have its own class for some matières — or
  // one class for all filières (the shared case).
  const needsFiliere =
    level !== undefined &&
    annee !== null &&
    hasFiliere(level.name, String(annee))
  const filiereOptions = needsFiliere
    ? [...new Set([...filiereDefaults(String(annee)), ...knownFilieres])]
    : []

  const anneeDone = annees.length === 0 || annee !== null
  const parcoursDone = forks.length === 0 || parcours !== null
  const slotDone = level !== undefined && anneeDone && parcoursDone
  const slotParcours = parcours === COMMUNE ? null : parcours
  // The filières this creation targets: one class each; none = commune (NULL).
  const selectedFilieres: (string | null)[] = !needsFiliere
    ? [null]
    : filieres.size > 0
      ? [...filieres]
      : [filiereDraft.trim() || null]
  const allFilieresSelected =
    filiereOptions.length > 0 &&
    filiereOptions.every((option) => filieres.has(option))

  const isCapable = (teacher: Teacher) =>
    subjectId !== null &&
    capabilities.some(
      (capability) =>
        capability.teacher_id === teacher.id &&
        capability.level_id === levelId &&
        capability.subject_id === subjectId &&
        (capability.annee === null || annee === null ||
          capability.annee === annee) &&
        (capability.parcours === null || slotParcours === null ||
          capability.parcours === slotParcours),
    )
  const orderedTeachers = [...teachers].sort(
    (a, b) => Number(isCapable(b)) - Number(isCapable(a)),
  )

  const pickLevel = (id: number) => {
    setLevelId(id)
    setAnnee(null)
    setParcours(null)
    setFilieres(new Set())
    setFiliereDraft("")
    setSubjectId(null)
    setSubjectDraft("")
    setTeacherId(null)
  }

  useEffect(() => {
    if (justAdded === null) return
    const timer = window.setTimeout(() => setJustAdded(null), 1400)
    return () => window.clearTimeout(timer)
  }, [justAdded])

  const addSubject = async () => {
    const name = subjectDraft.trim()
    if (!name || levelId === null) return
    const mine = levelSubjects.find(
      (subject) => subject.name.toLowerCase() === name.toLowerCase(),
    )
    try {
      const id = mine
        ? mine.id
        : (
            await apiSend<{ id: number }>("POST", "/api/subjects", {
              name,
              level_id: levelId,
            })
          ).id
      setSubjectDraft("")
      setSubjectId(id)
      setJustAdded(id)
      toast(`Matière « ${name} » ajoutée`)
      subjectInput.current?.focus()
      onDone()
    } catch (err) {
      setNote((err as Error).message)
    }
  }

  const submit = async () => {
    if (!slotDone || levelId === null) {
      setNote("Complétez le créneau : niveau, année, parcours.")
      return
    }
    if (subjectId === null) {
      setNote("Choisissez la matière (ou tapez-la puis Entrée).")
      return
    }
    let chosen = teacherId
    const typed = teacherDraft.trim()
    if (chosen === null && !typed) {
      setNote("Choisissez un professeur, ou tapez son nom pour le créer.")
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
      // One class per selected filière — « la même classe pour les autres
      // filières » in a single click. Empty selection = one classe commune.
      for (const filiere of selectedFilieres) {
        await apiSend("POST", "/api/classes", {
          level_id: levelId,
          subject_id: subjectId,
          teacher_id: chosen,
          annee,
          parcours: slotParcours,
          filiere,
        })
      }
      onOpenChange(false)
      onDone()
    } catch (err) {
      setNote((err as Error).message)
      setBusy(false)
    }
  }

  let step = 1
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Nouvelle classe</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Step number={step++} title="Le niveau">
            <div className="flex flex-wrap gap-1.5">
              {levels.map((entry) => (
                <StepChip
                  key={entry.id}
                  active={levelId === entry.id}
                  onClick={() => pickLevel(entry.id)}
                >
                  {entry.name}
                </StepChip>
              ))}
            </div>
          </Step>

          {level && annees.length > 0 && (
            <Step number={step++} title="L'année">
              <div className="flex flex-wrap gap-1.5">
                {annees.map(([value, label]) => (
                  <StepChip
                    key={value}
                    active={annee === Number(value)}
                    onClick={() => {
                      setAnnee(Number(value))
                      setParcours(null)
                      setTeacherId(null)
                    }}
                  >
                    {label}
                  </StepChip>
                ))}
              </div>
            </Step>
          )}

          {forks.length > 0 && (
            <Step number={step++} title="Le parcours">
              <div className="flex flex-wrap gap-1.5">
                {forks.map((fork) => (
                  <StepChip
                    key={fork}
                    active={parcours === fork}
                    onClick={() => {
                      setParcours(fork)
                      setTeacherId(null)
                    }}
                  >
                    {fork}
                  </StepChip>
                ))}
                <StepChip
                  active={parcours === COMMUNE}
                  onClick={() => {
                    setParcours(COMMUNE)
                    setTeacherId(null)
                  }}
                >
                  Classe commune ({forks.join(" + ")})
                </StepChip>
              </div>
            </Step>
          )}

          {needsFiliere && (
            <Step number={step++} title="La ou les filières">
              <div className="flex flex-wrap items-center gap-1.5">
                <label className="text-muted-foreground mr-1 flex items-center gap-1.5 text-xs">
                  <Checkbox
                    checked={allFilieresSelected}
                    onCheckedChange={(state) =>
                      setFilieres(
                        state === true ? new Set(filiereOptions) : new Set(),
                      )
                    }
                  />
                  Tout sélectionner
                </label>
                {filiereOptions.map((option) => (
                  <StepChip
                    key={option}
                    active={filieres.has(option)}
                    onClick={() =>
                      setFilieres((current) => {
                        const next = new Set(current)
                        if (next.has(option)) next.delete(option)
                        else next.add(option)
                        return next
                      })
                    }
                  >
                    {option}
                  </StepChip>
                ))}
                <Input
                  value={filiereDraft}
                  onChange={(event) => setFiliereDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && filiereDraft.trim()) {
                      event.preventDefault()
                      setFilieres((current) =>
                        new Set(current).add(filiereDraft.trim()),
                      )
                      setFiliereDraft("")
                    }
                  }}
                  placeholder="＋ filière…"
                  className="h-8 w-32 text-sm"
                />
              </div>
              <p className="text-muted-foreground mt-1.5 text-xs">
                {filieres.size > 1
                  ? `${filieres.size} classes seront créées — une par filière.`
                  : filieres.size === 1
                    ? "Une classe pour cette filière."
                    : "Aucune filière cochée = une classe commune à toutes les filières."}
              </p>
            </Step>
          )}

          {slotDone && (
            <Step number={step++} title="La matière">
              <div className="flex flex-wrap items-center gap-1.5">
                {level?.name === "Primaire" &&
                  !levelSubjects.some(
                    (subject) => subject.name === "Accompagnement complet",
                  ) && (
                    // Le Primaire est un seul groupe aidé sur tout : sa
                    // matière unique se crée ici. Aucune suggestion ailleurs.
                    <StepChip
                      active={false}
                      onClick={() => {
                        setSubjectDraft("Accompagnement complet")
                        void apiSend<{ id: number }>("POST", "/api/subjects", {
                          name: "Accompagnement complet",
                          level_id: levelId,
                        })
                          .then(({ id }) => {
                            setSubjectDraft("")
                            setSubjectId(id)
                            onDone()
                          })
                          .catch((err: Error) => setNote(err.message))
                      }}
                    >
                      ＋ Accompagnement complet (toutes matières)
                    </StepChip>
                  )}
                {levelSubjects.map((subject) => (
                  <StepChip
                    key={subject.id}
                    flash={justAdded === subject.id}
                    active={subjectId === subject.id}
                    onClick={() => {
                      setSubjectId(subject.id)
                      setSubjectDraft("")
                    }}
                  >
                    {subject.name}
                  </StepChip>
                ))}
                <Input
                  ref={subjectInput}
                  list="class-subject-options"
                  value={subjectDraft}
                  onChange={(event) => {
                    setSubjectDraft(event.target.value)
                    if (event.target.value) setSubjectId(null)
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault()
                      void addSubject()
                    }
                  }}
                  placeholder="＋ matière…"
                  className="h-8 w-36 text-sm"
                />
                <datalist id="class-subject-options">
                  {[...new Set(subjects.map((subject) => subject.name))].map(
                    (name) => (
                      <option key={name} value={name} />
                    ),
                  )}
                </datalist>
              </div>
            </Step>
          )}

          {slotDone && subjectId !== null && (
            <Step number={step++} title="Le professeur">
              <div className="flex flex-wrap items-center gap-1.5">
                {orderedTeachers.map((teacher) => (
                  <StepChip
                    key={teacher.id}
                    active={teacherId === teacher.id}
                    onClick={() => {
                      setTeacherId(teacher.id)
                      setTeacherDraft("")
                    }}
                  >
                    {teacher.name}
                    {isCapable(teacher) ? " ★" : ""}
                  </StepChip>
                ))}
                <Input
                  list="class-teacher-options"
                  value={teacherDraft}
                  onChange={(event) => {
                    setTeacherDraft(event.target.value)
                    if (event.target.value) setTeacherId(null)
                  }}
                  placeholder="＋ professeur…"
                  className="h-8 w-40 text-sm"
                />
                <datalist id="class-teacher-options">
                  {teachers.map((teacher) => (
                    <option key={teacher.id} value={teacher.name} />
                  ))}
                </datalist>
              </div>
              <p className="text-muted-foreground mt-1.5 text-xs">
                ★ = compétent pour ce créneau. Un nom nouveau crée le
                professeur ; sa compétence s'enregistre toute seule.
              </p>
            </Step>
          )}

          <Notice alert={note} />
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
  // Une classe, un professeur : un seul choix possible.
  const [successor, setSuccessor] = useState<number | null>(null)
  const [note, setNote] = useAlert()
  const [busy, setBusy] = useState(false)
  const vacant = target.teacher_id === null

  const submit = () => {
    if (successor === null) {
      setNote("Choisissez le professeur qui reprend la classe.")
      return
    }
    setNote(null)
    setBusy(true)
    apiSend("POST", `/api/classes/${target.id}/replace-teacher`, {
      date,
      successor_id: successor,
    })
      .then(onDone)
      .catch((err: Error) => {
        setNote(err.message)
        setBusy(false)
      })
  }

  const vacate = () => {
    setNote(null)
    setBusy(true)
    apiSend("POST", `/api/classes/${target.id}/vacate-teacher`, { date })
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
            {vacant
              ? `Nommer un professeur — ${target.subject_name}`
              : `Remplacer ${target.teacher_name} — ${target.subject_name}`}
          </DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          {vacant
            ? "La classe est sans professeur : ses jours vacants reviennent à " +
              "l'académie. Le professeur nommé est payé à partir de cette date."
            : `${target.teacher_name} est payé jusqu'à la veille de cette date, ` +
              "son successeur à partir de celle-ci — même quand un vieux mois " +
              "impayé se règle plus tard. L'ancien professeur peut ensuite être " +
              "archivé sans rien perdre."}
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
            <Label>
              {vacant ? "Qui prend la classe ?" : "Qui reprend la classe ?"}
            </Label>
            <div className="border-border max-h-44 space-y-1.5 overflow-y-auto rounded-lg border p-3">
              {teachers
                .filter((teacher) => teacher.id !== target.teacher_id)
                .map((teacher) => (
                  <label
                    key={teacher.id}
                    className="flex cursor-pointer items-center gap-2 text-sm"
                  >
                    <input
                      type="radio"
                      name="successeur"
                      checked={successor === teacher.id}
                      onChange={() => setSuccessor(teacher.id)}
                    />
                    {teacher.name}
                  </label>
                ))}
            </div>
            <p className="text-muted-foreground text-xs">
              Une classe, un professeur — s'ils doivent être deux, dédoublez la
              classe.
            </p>
          </div>
          <Notice alert={note} />
        </div>
        <DialogFooter className="flex-wrap gap-2">
          {!vacant && (
            <Button variant="outline" onClick={vacate} disabled={busy}>
              {busy ? "…" : "Laisser sans professeur"}
            </Button>
          )}
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : vacant ? "Nommer" : "Remplacer"}
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
  const [note, setNote] = useAlert()

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
        <Notice alert={note} />
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : "Créer le groupe"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
