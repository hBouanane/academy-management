// Create or edit a student: identity, école, tagged phones — the modal the
// client asked for. Enrollment (pack + matières) stays its own step.

import { useEffect, useState } from "react"
import { Plus, X } from "lucide-react"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Notice } from "@/components/Notice"
import { useAlert } from "@/lib/alert"
import { apiGet, apiSend } from "@/lib/api"
import type { Level, PhoneEntry, School, Student } from "@/lib/api"
import { fuzzyFilter } from "@/lib/fuzzy"
import {
  anneeOptions,
  filiereDefaults,
  hasFiliere,
  parcoursOptions,
} from "@/lib/levels"

const PHONE_TAGS = ["étudiant", "mère", "père", "tuteur", "autre"]

const phoneDigits = (number: string) => number.replace(/[\s.-]/g, "")
const phoneInvalid = (number: string) => !/^\d{10}$/.test(phoneDigits(number))

type Props = {
  levels: Level[]
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Present = edit that student; absent = create. */
  initial?: Student | null
  onSaved: (created?: {
    id: number
    name: string
    levelId: number
    annee: number | null
    parcours: string | null
    filiere: string | null
  }) => void
}

export function StudentDialog({
  levels,
  open,
  onOpenChange,
  initial,
  onSaved,
}: Props) {
  const [name, setName] = useState("")
  const [firstName, setFirstName] = useState("")
  const [levelId, setLevelId] = useState("")
  const [annee, setAnnee] = useState("")
  const [parcours, setParcours] = useState("")
  const [filiere, setFiliere] = useState("")
  const [school, setSchool] = useState("")
  const [phones, setPhones] = useState<PhoneEntry[]>([])
  const [schools, setSchools] = useState<School[]>([])
  const [filieres, setFilieres] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useAlert()

  useEffect(() => {
    if (!open) return
    apiGet<School[]>("/api/schools").then(setSchools).catch(() => {})
    apiGet<string[]>("/api/filieres").then(setFilieres).catch(() => {})
    setName(initial?.name ?? "")
    setFirstName(initial?.first_name ?? "")
    setLevelId(initial ? String(initial.level_id) : "")
    setAnnee(initial?.annee ? String(initial.annee) : "")
    setParcours(initial?.parcours ?? "")
    setFiliere(initial?.filiere ?? "")
    setSchool(initial?.school_name ?? "")
    setPhones(
      initial?.phone ? [{ tag: "étudiant", number: initial.phone }] : [],
    )
    if (initial) {
      apiGet<{ phones: PhoneEntry[] }>(`/api/students/${initial.id}/profile`)
        .then((profile) => setPhones(profile.phones))
        .catch(() => {})
    }
    setNote(null)
    setBusy(false)
  }, [open, initial, setNote])

  const levelName = levels.find((level) => String(level.id) === levelId)?.name ?? ""
  const annees = anneeOptions(levelName)
  const parcoursChoices = parcoursOptions(levelName, annee)

  const updatePhone = (index: number, patch: Partial<PhoneEntry>) =>
    setPhones((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    )

  const submit = () => {
    if (!name.trim()) return setNote("Le nom est obligatoire.")
    if (!levelId) return setNote("Choisissez un niveau.")
    const badPhone = phones.find((phone) => phoneInvalid(phone.number))
    if (badPhone)
      return setNote(
        `Le téléphone « ${badPhone.tag} » doit contenir exactement 10 chiffres.`,
      )
    setNote(null)
    setBusy(true)
    const body = {
      name: name.trim(),
      first_name: firstName.trim() || null,
      level_id: Number(levelId),
      annee: annee ? Number(annee) : null,
      parcours: parcoursChoices.length > 0 ? parcours || null : null,
      filiere: hasFiliere(levelName, annee) ? filiere.trim() || null : null,
      school: school.trim(),
      phones: phones.map((phone) => ({
        tag: phone.tag,
        number: phoneDigits(phone.number),
      })),
    }
    const request = initial
      ? apiSend("PATCH", `/api/students/${initial.id}`, body)
      : apiSend<{ id: number }>("POST", "/api/students", body)
    request
      .then((created) => {
        onOpenChange(false)
        onSaved(
          initial
            ? undefined
            : {
                id: (created as { id: number }).id,
                name: [firstName.trim(), name.trim()].filter(Boolean).join(" "),
                levelId: Number(levelId),
                annee: annee ? Number(annee) : null,
                parcours: parcoursChoices.length > 0 ? parcours || null : null,
                filiere: hasFiliere(levelName, annee)
                  ? filiere.trim() || null
                  : null,
              },
        )
      })
      .catch((err: Error) => {
        setNote(err.message)
        setBusy(false)
      })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {initial ? `Modifier ${initial.name}` : "Nouvel étudiant"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {!initial && (
            <ReturningStudent
              query={[firstName, name].filter(Boolean).join(" ")}
              onRestored={() => {
                onOpenChange(false)
                onSaved()
              }}
              onError={setNote}
            />
          )}
          <div className="flex gap-3">
            <div className="flex-1 space-y-2">
              <Label>Nom</Label>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Bouanane"
              />
            </div>
            <div className="flex-1 space-y-2">
              <Label>
                Prénom <span className="text-muted-foreground">(optionnel)</span>
              </Label>
              <Input
                value={firstName}
                onChange={(event) => setFirstName(event.target.value)}
                placeholder="Haitam"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <div className="min-w-32 flex-1 space-y-2">
              <Label>Niveau</Label>
              <Select
                value={levelId}
                onValueChange={(value) => {
                  setLevelId(value)
                  setAnnee("")
                  setFiliere("")
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
            <div className="min-w-32 flex-1 space-y-2">
              <Label>Année</Label>
              <Select value={annee} onValueChange={setAnnee}>
                <SelectTrigger className="w-full" disabled={!levelId}>
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
              <div className="min-w-40 flex-1 space-y-2">
                <Label>Filière</Label>
                <Input
                  list="filiere-options"
                  value={filiere}
                  onChange={(event) => setFiliere(event.target.value)}
                  placeholder="Choisir ou saisir une filière"
                />
                <datalist id="filiere-options">
                  {[...new Set([...filiereDefaults(annee), ...filieres])].map(
                    (option) => (
                      <option key={option} value={option} />
                    ),
                  )}
                </datalist>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <Label>
              École <span className="text-muted-foreground">(optionnel)</span>
            </Label>
            <Input
              list="school-options"
              value={school}
              onChange={(event) => setSchool(event.target.value)}
              placeholder="Choisir ou saisir une école"
            />
            <datalist id="school-options">
              {schools.map((entry) => (
                <option key={entry.id} value={entry.name} />
              ))}
            </datalist>
          </div>

          <div className="space-y-2">
            <Label>Téléphones</Label>
            {phones.map((phone, index) => (
              <div key={index} className="flex items-center gap-2">
                <Select
                  value={phone.tag}
                  onValueChange={(tag) => updatePhone(index, { tag })}
                >
                  <SelectTrigger className="w-28">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PHONE_TAGS.map((tag) => (
                      <SelectItem key={tag} value={tag}>
                        {tag}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  value={phone.number}
                  onChange={(event) =>
                    updatePhone(index, { number: event.target.value })
                  }
                  placeholder="06 61 23 45 67"
                  className="flex-1"
                />
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    setPhones((current) => current.filter((_, i) => i !== index))
                  }
                >
                  <X className="size-4" />
                </Button>
              </div>
            ))}
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                setPhones((current) => [
                  ...current,
                  { tag: current.length === 0 ? "étudiant" : "mère", number: "" },
                ])
              }
            >
              <Plus className="size-4" /> Ajouter un téléphone
            </Button>
          </div>

          <Notice alert={note} />
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : initial ? "Enregistrer" : "Créer et inscrire"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Déjà venu ? — recherche tolérante sur TOUS les élèves, archivés compris.
    Un élève qui revient après deux ans se retrouve ici avec ses impayés :
    on le réactive au lieu d'en créer un doublon, et on sait quoi lui
    réclamer avant de le réinscrire. */
function ReturningStudent({
  query,
  onRestored,
  onError,
}: {
  query: string
  onRestored: () => void
  onError: (message: string) => void
}) {
  const [all, setAll] = useState<Student[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    apiGet<Student[]>("/api/students?include_inactive=true")
      .then(setAll)
      .catch(() => {})
  }, [])

  const matches =
    query.trim().length < 2
      ? []
      : fuzzyFilter(all, query, (student) =>
          [student.first_name, student.name, student.school_name]
            .filter(Boolean)
            .join(" "),
        ).slice(0, 4)

  if (matches.length === 0) return null

  const restore = (student: Student) => {
    setBusy(true)
    apiSend("PATCH", `/api/students/${student.id}`, { is_active: true })
      .then(onRestored)
      .catch((err: Error) => onError(err.message))
      .finally(() => setBusy(false))
  }

  return (
    <div className="border-border space-y-2 rounded-xl border border-dashed p-3">
      <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        Déjà dans vos fiches ?
      </p>
      {matches.map((student) => (
        <div
          key={student.id}
          className="flex flex-wrap items-center justify-between gap-2 text-sm"
        >
          <span className="min-w-0">
            <span className="font-medium">
              {[student.first_name, student.name].filter(Boolean).join(" ")}
            </span>
            <span className="text-muted-foreground text-xs">
              {" "}
              · {student.level_name}
              {student.school_name ? ` · ${student.school_name}` : ""}
              {student.is_active ? "" : " · archivé"}
            </span>
            {Number(student.unpaid_months) > 0 && (
              <span className="text-destructive block text-xs">
                {student.unpaid_months} mois impayé(s) — à régler avant de le
                réinscrire
              </span>
            )}
          </span>
          {student.is_active ? (
            <span className="text-muted-foreground shrink-0 text-xs">
              déjà actif
            </span>
          ) : (
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => restore(student)}
            >
              Réactiver sa fiche
            </Button>
          )}
        </div>
      ))}
    </div>
  )
}
