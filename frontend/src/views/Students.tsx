import { useCallback, useEffect, useState } from "react"
import { Pencil, UserMinus, UserPlus } from "lucide-react"
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
import { EnrollDialog } from "@/components/EnrollDialog"
import { Notice } from "@/components/Notice"
import { PayDialog } from "@/components/PayDialog"
import { apiGet, apiSend } from "@/lib/api"
import type { Level, Student } from "@/lib/api"

const phoneDigits = (phone: string) => phone.replace(/[\s.-]/g, "")
const phoneInvalid = (phone: string) =>
  phone !== "" && !/^\d{10}$/.test(phoneDigits(phone))

type Props = { month: string }

export function Students({ month }: Props) {
  const [students, setStudents] = useState<Student[]>([])
  const [levels, setLevels] = useState<Level[]>([])
  const [showInactive, setShowInactive] = useState(false)
  const [name, setName] = useState("")
  const [phone, setPhone] = useState("")
  const [levelId, setLevelId] = useState<string>("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Student | null>(null)
  const [editValues, setEditValues] = useState({ name: "", phone: "", level_id: "" })
  // Right after creating a student, we open enrollment directly — the natural
  // next step is always "subscribe him for this month".
  const [justCreated, setJustCreated] = useState<{
    id: number
    name: string
    levelId: number
  } | null>(null)
  // A fresh enrollment chains straight into its pay dialog (réductions incluses).
  const [payTarget, setPayTarget] = useState<{ id: number; name: string } | null>(
    null,
  )

  const reload = useCallback(() => {
    apiGet<Student[]>(
      `/api/students?include_inactive=${showInactive}&month=${month}`,
    )
      .then(setStudents)
      .catch((err: Error) => setError(err.message))
  }, [showInactive, month])

  useEffect(() => {
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
  }, [])
  useEffect(reload, [reload])

  const run = (action: () => Promise<unknown>) => {
    setError(null)
    setBusy(true)
    action()
      .then(reload)
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  const addStudent = () => {
    if (phoneInvalid(phone)) {
      setError("Le téléphone doit contenir exactement 10 chiffres.")
      return
    }
    setError(null)
    setBusy(true)
    apiSend<{ id: number }>("POST", "/api/students", {
      name,
      level_id: Number(levelId),
      phone: phoneDigits(phone) || null,
    })
      .then((created) => {
        setJustCreated({ id: created.id, name, levelId: Number(levelId) })
        setName("")
        setPhone("")
        setLevelId("")
        reload()
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  const saveEdit = () => {
    if (phoneInvalid(editValues.phone)) {
      setError("Le téléphone doit contenir exactement 10 chiffres.")
      return
    }
    run(async () => {
      if (!editing) return
      await apiSend("PATCH", `/api/students/${editing.id}`, {
        name: editValues.name,
        phone: phoneDigits(editValues.phone), // "" means "clear it"
        level_id: Number(editValues.level_id),
      })
      setEditing(null)
    })
  }

  const setActive = (student: Student, active: boolean) =>
    run(() => apiSend("PATCH", `/api/students/${student.id}`, { is_active: active }))

  return (
    <div className="view-enter space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Étudiants</h2>
        <p className="text-muted-foreground text-sm">
          Après création, l'inscription du mois s'ouvre directement
        </p>
      </header>

      <Notice message={error} />

      <div className="surface-card space-y-3 p-5">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Nouvel étudiant
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <Input
            placeholder="Nom complet"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-56"
          />
          <Select value={levelId} onValueChange={setLevelId}>
            <SelectTrigger className="w-40">
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
          <Input
            placeholder="Téléphone (optionnel)"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            className="w-44"
          />
          <Button onClick={addStudent} disabled={!name || !levelId || busy}>
            <UserPlus className="size-4" /> Créer et inscrire
          </Button>
        </div>
      </div>

      <div className="surface-card p-5">
        <label className="text-muted-foreground mb-4 flex items-center gap-2 text-sm">
          <Checkbox
            checked={showInactive}
            onCheckedChange={(checked) => setShowInactive(checked === true)}
          />
          Afficher les étudiants désactivés
        </label>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nom</TableHead>
              <TableHead>Niveau</TableHead>
              <TableHead>Téléphone</TableHead>
              <TableHead>Impayés</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {students.map((student, index) => (
              <TableRow
                key={student.id}
                className={`stagger-row ${Number(student.unpaid_months) > 0 ? "row-unpaid" : ""}`}
                style={{ animationDelay: `${index * 40}ms` }}
              >
                <TableCell className="font-medium">{student.name}</TableCell>
                <TableCell>{student.level_name}</TableCell>
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
                  {student.is_active ? (
                    <Badge className="bg-success/15 text-success border-success/20 border">
                      Actif
                    </Badge>
                  ) : (
                    <Badge variant="outline">Désactivé</Badge>
                  )}
                </TableCell>
                <TableCell className="space-x-1 text-right">
                  {student.is_active ? (
                    <EnrollDialog
                      studentId={student.id}
                      studentName={student.name}
                      levelId={student.level_id}
                      month={month}
                      onDone={reload}
                      onEnrolled={(id) =>
                        setPayTarget({ id, name: student.name })
                      }
                    />
                  ) : null}
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Modifier"
                    onClick={() => {
                      setEditing(student)
                      setEditValues({
                        name: student.name,
                        phone: student.phone ?? "",
                        level_id: String(student.level_id),
                      })
                    }}
                  >
                    <Pencil className="size-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    title={
                      student.is_active
                        ? "Désactiver (l'historique reste)"
                        : "Réactiver"
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
          </TableBody>
        </Table>
        <p className="text-muted-foreground mt-3 text-xs">
          Un étudiant n'est jamais supprimé : désactivé, il disparaît des listes
          mais tout son historique de paiements reste.
        </p>
      </div>

      {justCreated && (
        <EnrollDialog
          studentId={justCreated.id}
          studentName={justCreated.name}
          levelId={justCreated.levelId}
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

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Modifier {editing?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Nom</Label>
              <Input
                value={editValues.name}
                onChange={(event) =>
                  setEditValues((current) => ({ ...current, name: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Niveau</Label>
              <Select
                value={editValues.level_id}
                onValueChange={(value) =>
                  setEditValues((current) => ({ ...current, level_id: value }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
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
            <div className="space-y-2">
              <Label>Téléphone</Label>
              <Input
                value={editValues.phone}
                onChange={(event) =>
                  setEditValues((current) => ({ ...current, phone: event.target.value }))
                }
              />
            </div>
          </div>
          <DialogFooter>
            <Button onClick={saveEdit} disabled={busy}>
              Enregistrer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
