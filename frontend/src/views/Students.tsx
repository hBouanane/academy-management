import { useCallback, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
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
import { apiGet, apiSend } from "@/lib/api"
import type { Level, Student } from "@/lib/api"

export function Students() {
  const [students, setStudents] = useState<Student[]>([])
  const [levels, setLevels] = useState<Level[]>([])
  const [showInactive, setShowInactive] = useState(false)
  const [name, setName] = useState("")
  const [phone, setPhone] = useState("")
  const [levelId, setLevelId] = useState<string>("")
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    apiGet<Student[]>(`/api/students?include_inactive=${showInactive}`)
      .then(setStudents)
      .catch((err: Error) => setError(err.message))
  }, [showInactive])

  useEffect(() => {
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
  }, [])
  useEffect(reload, [reload])

  const addStudent = () => {
    setError(null)
    apiSend("POST", "/api/students", {
      name,
      level_id: Number(levelId),
      phone: phone || null,
    })
      .then(() => {
        setName("")
        setPhone("")
        reload()
      })
      .catch((err: Error) => setError(err.message))
  }

  const setActive = (student: Student, active: boolean) => {
    apiSend("PATCH", `/api/students/${student.id}`, { is_active: active })
      .then(reload)
      .catch((err: Error) => setError(err.message))
  }

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Étudiants</h2>
        <p className="text-muted-foreground text-sm">
          Les étudiants sont désactivés, jamais supprimés — l'historique reste.
        </p>
      </header>

      {error && <p className="text-destructive text-sm">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Ajouter un étudiant</CardTitle>
        </CardHeader>
        <div className="flex flex-wrap items-end gap-3 px-6 pb-6">
          <div className="w-56">
            <Input
              placeholder="Nom complet"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
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
          <div className="w-44">
            <Input
              placeholder="Téléphone (optionnel)"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
            />
          </div>
          <Button onClick={addStudent} disabled={!name || !levelId}>
            Ajouter
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Liste</CardTitle>
          <CardDescription>
            <label className="flex items-center gap-2">
              <Checkbox
                checked={showInactive}
                onCheckedChange={(checked) => setShowInactive(checked === true)}
              />
              Afficher les étudiants désactivés
            </label>
          </CardDescription>
        </CardHeader>
        <div className="px-6 pb-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nom</TableHead>
                <TableHead>Niveau</TableHead>
                <TableHead>Téléphone</TableHead>
                <TableHead>Statut</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {students.map((student) => (
                <TableRow key={student.id}>
                  <TableCell className="font-medium">{student.name}</TableCell>
                  <TableCell>{student.level_name}</TableCell>
                  <TableCell>{student.phone ?? "—"}</TableCell>
                  <TableCell>
                    {student.is_active ? (
                      <Badge>Actif</Badge>
                    ) : (
                      <Badge variant="outline">Désactivé</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setActive(student, !student.is_active)}
                    >
                      {student.is_active ? "Désactiver" : "Réactiver"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  )
}
