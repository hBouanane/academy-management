import { useCallback, useEffect, useState } from "react"
import { Pencil, UserMinus, UserPlus } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { EnrollDialog } from "@/components/EnrollDialog"
import { LevelFilter, matchesLevelFilter } from "@/components/LevelFilter"
import type { LevelFilterValue } from "@/components/LevelFilter"
import { MonthNav } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { PayDialog } from "@/components/PayDialog"
import { StudentDialog } from "@/components/StudentDialog"
import { StudentProfile } from "@/components/StudentProfile"
import { Input } from "@/components/ui/input"
import { apiGet, apiSend } from "@/lib/api"
import type { Level, Student } from "@/lib/api"
import { fuzzyFilter } from "@/lib/fuzzy"
import { anneeLabel } from "@/lib/levels"
import { formatDH } from "@/lib/money"
import { useAlert } from "@/lib/alert"

const fullName = (student: {
  first_name: string | null
  name: string
  school_name?: string | null
}) =>
  [student.first_name, student.name, student.school_name]
    .filter(Boolean)
    .join(" ")

type Props = { month: string; setMonth: (month: string) => void }

export function Students({ month, setMonth }: Props) {
  const [students, setStudents] = useState<Student[]>([])
  const [levels, setLevels] = useState<Level[]>([])
  const [filter, setFilter] = useState<LevelFilterValue>({
    levelId: null,
    annee: null,
  })
  const [showInactive, setShowInactive] = useState(false)
  const [search, setSearch] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useAlert()
  // The student modal: null closed, "new" creating, a Student editing.
  const [editing, setEditing] = useState<Student | "new" | null>(null)
  const [profileId, setProfileId] = useState<number | null>(null)
  // Right after creating a student, enrollment opens directly; after
  // enrolling, the pay dialog chains in turn.
  const [justCreated, setJustCreated] = useState<{
    id: number
    name: string
    levelId: number
    annee: number | null
    parcours: string | null
    filiere: string | null
  } | null>(null)
  const [payTarget, setPayTarget] = useState<{ id: number; name: string } | null>(
    null,
  )

  const reload = useCallback(() => {
    setError(null)
    apiGet<Student[]>(
      `/api/students?include_inactive=${showInactive}&month=${month}`,
    )
      .then(setStudents)
      .catch((err: Error) => setError(err.message))
  }, [showInactive, month, setError])

  useEffect(() => {
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
  }, [])
  useEffect(reload, [reload])

  const setActive = (student: Student, active: boolean) => {
    setError(null)
    setBusy(true)
    apiSend("PATCH", `/api/students/${student.id}`, { is_active: active })
      .then(reload)
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Étudiants</h2>
          <p className="text-muted-foreground text-sm">
            Cliquez un nom pour ouvrir le profil complet
          </p>
        </div>
        <div className="flex items-center gap-2">
          <MonthNav month={month} setMonth={setMonth} />
          <Button onClick={() => setEditing("new")}>
            <UserPlus className="size-4" /> Nouvel étudiant
          </Button>
        </div>
      </header>

      <Notice alert={error} />

      <div className="surface-card p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <LevelFilter levels={levels} value={filter} onChange={setFilter} />
          <div className="flex flex-wrap items-center gap-3">
            <Input
              placeholder="Rechercher…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-56"
            />
            <label className="text-muted-foreground flex items-center gap-2 text-sm">
              <Checkbox
                checked={showInactive}
                onCheckedChange={(checked) => setShowInactive(checked === true)}
              />
              Afficher les étudiants archivés
            </label>
          </div>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nom</TableHead>
              <TableHead>Niveau</TableHead>
              <TableHead>Téléphone</TableHead>
              <TableHead>Impayés</TableHead>
              <TableHead>Ce mois</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {fuzzyFilter(
              students.filter((s) => matchesLevelFilter(filter, s)),
              search,
              fullName,
            ).map((student, index) => (
              <TableRow
                key={student.id}
                className={`stagger-row cursor-pointer ${Number(student.unpaid_months) > 0 ? "row-unpaid" : ""}`}
                style={{ animationDelay: `${index * 40}ms` }}
                title="Ouvrir le profil"
                onClick={(event) => {
                  // Anywhere on the row opens the profile — except the
                  // buttons, and except clicks inside portaled dialogs
                  // (React bubbles those through the row even though they
                  // render elsewhere in the DOM).
                  const target = event.target as HTMLElement
                  if (!event.currentTarget.contains(target)) return
                  if (target.closest("button, a")) return
                  setProfileId(student.id)
                }}
              >
                <TableCell>
                  <p className="font-medium">
                    {[student.first_name, student.name].filter(Boolean).join(" ")}
                  </p>
                  {student.school_name && (
                    <p className="text-muted-foreground text-xs">
                      {student.school_name}
                    </p>
                  )}
                </TableCell>
                <TableCell>
                  {student.level_name}
                  {student.annee !== null && (
                    <p className="text-muted-foreground text-xs">
                      {anneeLabel(student.level_name, student.annee)}
                      {student.filiere ? ` · ${student.filiere}` : ""}
                    </p>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {student.phone ?? "—"}
                </TableCell>
                <TableCell>
                  {Number(student.unpaid_months) > 0 ? (
                    <Badge variant="destructive">
                      {student.unpaid_months} mois
                    </Badge>
                  ) : (
                    <span className="text-muted-foreground text-xs">—</span>
                  )}
                </TableCell>
                <TableCell>
                  {student.month_enrollment_id === null ? (
                    <span className="text-muted-foreground text-xs">
                      Non inscrit
                    </span>
                  ) : student.month_paid &&
                    student.month_remaining_centimes > 0 ? (
                    <Badge className="border-amber-500/25 bg-amber-500/15 text-amber-600 border">
                      Avance · reste {formatDH(student.month_remaining_centimes)}
                    </Badge>
                  ) : student.month_paid ? (
                    <Badge className="bg-success/15 text-success border-success/20 border">
                      Payé
                    </Badge>
                  ) : (
                    <Badge variant="destructive">Impayé</Badge>
                  )}
                </TableCell>
                <TableCell>
                  {!student.ever_enrolled ? (
                    <Badge className="bg-secondary text-secondary-foreground">
                      Pré-inscrit
                    </Badge>
                  ) : student.is_active ? (
                    <Badge className="bg-success/15 text-success border-success/20 border">
                      Actif
                    </Badge>
                  ) : (
                    <Badge variant="outline">Archivé</Badge>
                  )}
                </TableCell>
                <TableCell className="space-x-1 text-right">
                  {student.is_active && student.month_enrollment_id === null && (
                    <EnrollDialog
                      studentId={student.id}
                      studentName={student.name}
                      levelId={student.level_id}
                      annee={student.annee}
                      parcours={student.parcours}
                      filiere={student.filiere}
                      month={month}
                      onDone={reload}
                      onEnrolled={(id) =>
                        setPayTarget({ id, name: student.name })
                      }
                    />
                  )}
                  {student.month_enrollment_id !== null &&
                    !student.month_paid && (
                      <PayDialog
                        enrollmentId={student.month_enrollment_id}
                        studentName={student.name}
                        onDone={reload}
                      />
                    )}
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Modifier"
                    onClick={() => setEditing(student)}
                  >
                    <Pencil className="size-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    title={
                      student.is_active
                        ? "Archiver (l'historique reste)"
                        : "Restaurer"
                    }
                    onClick={() => setActive(student, !student.is_active)}
                  >
                    {student.is_active ? (
                      <UserMinus className="size-4" />
                    ) : (
                      <UserPlus className="size-4" />
                    )}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {students.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={7}
                  className="text-muted-foreground text-center"
                >
                  Aucun étudiant — créez le premier.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        <p className="text-muted-foreground mt-3 text-xs">
          Un étudiant n'est jamais supprimé : archivé, il disparaît des listes
          mais son profil et tout son historique restent consultables.
        </p>
      </div>

      <StudentDialog
        levels={levels}
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        initial={editing === "new" ? null : editing}
        onSaved={(created) => {
          setEditing(null)
          reload()
          if (created) setJustCreated(created)
        }}
      />

      <StudentProfile
        studentId={profileId}
        onClose={() => setProfileId(null)}
        onChanged={reload}
      />

      {justCreated && (
        <EnrollDialog
          studentId={justCreated.id}
          studentName={justCreated.name}
          levelId={justCreated.levelId}
          annee={justCreated.annee}
          parcours={justCreated.parcours}
          filiere={justCreated.filiere}
          month={month}
          open={justCreated !== null}
          onOpenChange={(open) => {
            if (!open) setJustCreated(null)
          }}
          onDone={() => {
            setJustCreated(null)
            reload()
          }}
          onEnrolled={(id) => setPayTarget({ id, name: justCreated.name })}
        />
      )}

      {payTarget && (
        <PayDialog
          enrollmentId={payTarget.id}
          studentName={payTarget.name}
          open
          onOpenChange={(next) => {
            if (!next) setPayTarget(null)
          }}
          onDone={() => {
            setPayTarget(null)
            reload()
          }}
        />
      )}
    </div>
  )
}
