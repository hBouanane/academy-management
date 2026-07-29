import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { apiGet, apiSend } from "@/lib/api"
import type {
  Academy,
  ClassRow,
  Level,
  Package,
  Subject,
  Teacher,
} from "@/lib/api"
import { dhToCentimes, formatDH } from "@/lib/money"

export function Settings() {
  const [error, setError] = useState<string | null>(null)
  // Bumped whenever a card creates something, so sibling cards refetch
  // (e.g. a new subject must appear in the class form immediately).
  const [version, setVersion] = useState(0)
  const changed = () => setVersion((current) => current + 1)
  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Paramètres</h2>
        <p className="text-muted-foreground text-sm">
          Académie, matières, professeurs, classes et forfaits
        </p>
      </header>
      {error && <p className="text-destructive text-sm">{error}</p>}
      <div className="grid gap-6 xl:grid-cols-2">
        <AcademyCard onError={setError} />
        <PackagesCard onError={setError} onChanged={changed} />
        <SubjectsCard onError={setError} onChanged={changed} />
        <TeachersCard onError={setError} onChanged={changed} />
      </div>
      <ClassesCard onError={setError} version={version} />
    </div>
  )
}

type CardProps = { onError: (message: string | null) => void }
type MutatingCardProps = CardProps & { onChanged: () => void }

function AcademyCard({ onError }: CardProps) {
  const [academy, setAcademy] = useState<Academy | null>(null)
  const [name, setName] = useState("")
  const [venuePct, setVenuePct] = useState("")
  const [ownerPct, setOwnerPct] = useState("")

  useEffect(() => {
    apiGet<Academy[]>("/api/academies")
      .then(([first]) => {
        if (!first) return
        setAcademy(first)
        setName(first.name)
        setVenuePct(String(first.venue_bp / 100))
        setOwnerPct(String(first.owner_bp / 100))
      })
      .catch((err: Error) => onError(err.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const venue = Number(venuePct)
  const owner = Number(ownerPct)
  const splitValid =
    venuePct !== "" &&
    ownerPct !== "" &&
    Number.isFinite(venue) &&
    Number.isFinite(owner) &&
    venue >= 0 &&
    owner >= 0 &&
    venue + owner <= 100

  const save = () => {
    if (!academy || !splitValid) return
    onError(null)
    apiSend("PATCH", `/api/academies/${academy.id}`, {
      name,
      venue_bp: Math.round(venue * 100),
      owner_bp: Math.round(owner * 100),
    })
      .then((updated) => setAcademy(updated as Academy))
      .catch((err: Error) => onError(err.message))
  }

  const teacherPct = splitValid ? 100 - venue - owner : 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>Académie</CardTitle>
        <CardDescription>
          Répartition par défaut d'un paiement — les professeurs se partagent le
          reste ({teacherPct}%) à parts égales par matière
        </CardDescription>
      </CardHeader>
      <div className="space-y-4 px-6 pb-6">
        <div className="space-y-2">
          <Label>Nom de l'académie</Label>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div className="flex gap-4">
          <div className="space-y-2">
            <Label>Part salle (%)</Label>
            <Input
              type="number"
              min="0"
              max="100"
              value={venuePct}
              onChange={(event) => setVenuePct(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Part propriétaire (%)</Label>
            <Input
              type="number"
              min="0"
              max="100"
              value={ownerPct}
              onChange={(event) => setOwnerPct(event.target.value)}
            />
          </div>
        </div>
        {!splitValid && (
          <p className="text-destructive text-sm">
            Les pourcentages doivent être positifs et leur somme au plus 100.
          </p>
        )}
        <Button onClick={save} disabled={!academy || !splitValid}>
          Enregistrer
        </Button>
      </div>
    </Card>
  )
}

function SubjectsCard({ onError, onChanged }: MutatingCardProps) {
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [name, setName] = useState("")

  const reload = useCallback(() => {
    apiGet<Subject[]>("/api/subjects").then(setSubjects).catch(() => {})
  }, [])
  useEffect(reload, [reload])

  const add = () => {
    onError(null)
    apiSend("POST", "/api/subjects", { name })
      .then(() => {
        setName("")
        reload()
        onChanged()
      })
      .catch((err: Error) => onError(err.message))
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Matières</CardTitle>
      </CardHeader>
      <div className="space-y-3 px-6 pb-6">
        <div className="flex gap-2">
          <Input
            placeholder="Mathématiques…"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Button onClick={add} disabled={!name}>
            Ajouter
          </Button>
        </div>
        <p className="text-muted-foreground text-sm">
          {subjects.map((subject) => subject.name).join(" · ") || "Aucune matière"}
        </p>
      </div>
    </Card>
  )
}

function TeachersCard({ onError, onChanged }: MutatingCardProps) {
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [name, setName] = useState("")
  const [phone, setPhone] = useState("")

  const reload = useCallback(() => {
    apiGet<Teacher[]>("/api/teachers").then(setTeachers).catch(() => {})
  }, [])
  useEffect(reload, [reload])

  const add = () => {
    onError(null)
    apiSend("POST", "/api/teachers", { name, phone: phone || null })
      .then(() => {
        setName("")
        setPhone("")
        reload()
        onChanged()
      })
      .catch((err: Error) => onError(err.message))
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Professeurs</CardTitle>
      </CardHeader>
      <div className="space-y-3 px-6 pb-6">
        <div className="flex gap-2">
          <Input
            placeholder="Nom"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Input
            placeholder="Téléphone"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            className="w-40"
          />
          <Button onClick={add} disabled={!name}>
            Ajouter
          </Button>
        </div>
        <p className="text-muted-foreground text-sm">
          {teachers.map((teacher) => teacher.name).join(" · ") ||
            "Aucun professeur"}
        </p>
      </div>
    </Card>
  )
}

function PackagesCard({ onError, onChanged }: MutatingCardProps) {
  const [packages, setPackages] = useState<Package[]>([])
  const [count, setCount] = useState("1")
  const [price, setPrice] = useState("")

  const reload = useCallback(() => {
    apiGet<Package[]>("/api/packages").then(setPackages).catch(() => {})
  }, [])
  useEffect(reload, [reload])

  const add = () => {
    onError(null)
    apiSend("POST", "/api/packages", {
      subject_count: Number(count),
      monthly_price_centimes: dhToCentimes(price),
    })
      .then(() => {
        setPrice("")
        reload()
        onChanged()
      })
      .catch((err: Error) => onError(err.message))
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Forfaits</CardTitle>
        <CardDescription>Prix mensuel par nombre de matières</CardDescription>
      </CardHeader>
      <div className="space-y-3 px-6 pb-6">
        <div className="flex gap-2">
          <Input
            type="number"
            min="1"
            max="8"
            value={count}
            onChange={(event) => setCount(event.target.value)}
            className="w-20"
          />
          <Input
            type="number"
            min="0"
            placeholder="Prix en DH"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
          />
          <Button onClick={add} disabled={!price}>
            Ajouter
          </Button>
        </div>
        <p className="text-muted-foreground text-sm">
          {packages
            .map(
              (pack) =>
                `${pack.subject_count} mat. = ${formatDH(pack.monthly_price_centimes)}`,
            )
            .join(" · ") || "Aucun forfait"}
        </p>
      </div>
    </Card>
  )
}

function ClassesCard({ onError, version }: CardProps & { version: number }) {
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [levels, setLevels] = useState<Level[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [levelId, setLevelId] = useState("")
  const [subjectId, setSubjectId] = useState("")
  const [teacherId, setTeacherId] = useState("")

  const reload = useCallback(() => {
    apiGet<ClassRow[]>("/api/classes").then(setClasses).catch(() => {})
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
    apiGet<Subject[]>("/api/subjects").then(setSubjects).catch(() => {})
    apiGet<Teacher[]>("/api/teachers").then(setTeachers).catch(() => {})
  }, [])
  // version bumps when sibling cards create subjects/teachers/packages.
  useEffect(reload, [reload, version])

  const add = () => {
    onError(null)
    apiSend("POST", "/api/classes", {
      level_id: Number(levelId),
      subject_id: Number(subjectId),
      teacher_id: Number(teacherId),
    })
      .then(reload)
      .catch((err: Error) => onError(err.message))
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Classes</CardTitle>
        <CardDescription>
          Une classe = une matière enseignée par un professeur à un niveau
        </CardDescription>
      </CardHeader>
      <div className="space-y-4 px-6 pb-6">
        <div className="flex flex-wrap gap-2">
          <PickSelect
            placeholder="Niveau"
            value={levelId}
            onChange={setLevelId}
            options={levels.map((level) => [String(level.id), level.name])}
          />
          <PickSelect
            placeholder="Matière"
            value={subjectId}
            onChange={setSubjectId}
            options={subjects.map((subject) => [String(subject.id), subject.name])}
          />
          <PickSelect
            placeholder="Professeur"
            value={teacherId}
            onChange={setTeacherId}
            options={teachers.map((teacher) => [String(teacher.id), teacher.name])}
          />
          <Button onClick={add} disabled={!levelId || !subjectId || !teacherId}>
            Ajouter la classe
          </Button>
        </div>
        <p className="text-muted-foreground text-sm">
          {classes
            .map(
              (row) =>
                `${row.subject_name} — ${row.teacher_name} (${row.level_name})`,
            )
            .join(" · ") || "Aucune classe"}
        </p>
      </div>
    </Card>
  )
}

function PickSelect({
  placeholder,
  value,
  onChange,
  options,
}: {
  placeholder: string
  value: string
  onChange: (value: string) => void
  options: [string, string][]
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-44">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map(([optionValue, label]) => (
          <SelectItem key={optionValue} value={optionValue}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

