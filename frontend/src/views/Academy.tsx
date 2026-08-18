import { useCallback, useEffect, useState } from "react"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
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
import { TeacherDialog } from "@/components/TeacherDialog"
import { apiGet, apiSend } from "@/lib/api"
import type { Academy as AcademyType, Teacher } from "@/lib/api"
import { useAlert } from "@/lib/alert"

// Even prorata ladder: 3 tranches -> 100/67/33, 4 -> 100/75/50/25 — the
// automatic default whenever a tranche is added or removed, editable after.
const ladder = (count: number) =>
  Array.from({ length: count }, (_, index) =>
    String(Math.round(((count - index) / count) * 100)),
  )

export function Academy() {
  const [academy, setAcademy] = useState<AcademyType | null>(null)
  const [name, setName] = useState("")
  const [venuePct, setVenuePct] = useState("")
  const [ownerPct, setOwnerPct] = useState("")
  const [segments, setSegments] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useAlert()

  useEffect(() => {
    apiGet<AcademyType[]>("/api/academies")
      .then(([first]) => {
        if (!first) return
        setAcademy(first)
        setName(first.name)
        setVenuePct(String(first.venue_bp / 100))
        setOwnerPct(String(first.owner_bp / 100))
        setSegments(first.proration_bp.map((bp) => String(bp / 100)))
      })
      .catch((err: Error) => setError(err.message))
  }, [setError])

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
  const teacherPct = splitValid ? 100 - venue - owner : 0

  const segmentsValid =
    segments.length >= 1 &&
    segments.every((segment) => {
      const value = Number(segment.replace(",", "."))
      return Number.isFinite(value) && value >= 0 && value <= 100
    })

  const save = () => {
    if (!academy || !splitValid || !segmentsValid) return
    setError(null)
    setBusy(true)
    setSaved(false)
    apiSend("PATCH", `/api/academies/${academy.id}`, {
      name,
      venue_bp: Math.round(venue * 100),
      owner_bp: Math.round(owner * 100),
      proration_bp: segments.map((segment) =>
        Math.round(Number(segment.replace(",", ".")) * 100),
      ),
    })
      .then((updated) => {
        setAcademy(updated as AcademyType)
        setSaved(true)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  return (
    <div className="view-enter max-w-2xl space-y-6">
      <header>
        <h2 className="text-2xl font-semibold tracking-tight">Académie</h2>
        <p className="text-muted-foreground text-sm">
          La répartition par défaut de chaque paiement — modifiable à tout
          moment, sans jamais toucher aux mois déjà encaissés
        </p>
      </header>

      <Notice alert={error} />

      <div className="surface-card space-y-5 p-6">
        <div className="space-y-2">
          <Label>Nom de l'académie</Label>
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div className="flex gap-4">
          <div className="flex-1 space-y-2">
            <Label>Part salle (%)</Label>
            <Input
              type="number"
              min="0"
              max="100"
              value={venuePct}
              onChange={(event) => setVenuePct(event.target.value)}
            />
          </div>
          <div className="flex-1 space-y-2">
            <Label>Part propriétaire (%)</Label>
            <Input
              type="number"
              min="0"
              max="100"
              value={ownerPct}
              onChange={(event) => setOwnerPct(event.target.value)}
            />
          </div>
          <div className="flex-1 space-y-2">
            <Label className="text-muted-foreground">Part professeurs</Label>
            <div className="border-border text-muted-foreground flex h-9 items-center rounded-lg border border-dashed px-3 text-sm">
              {splitValid ? `${teacherPct}% (partagé par matière)` : "—"}
            </div>
          </div>
        </div>
        <Notice
          message={
            splitValid
              ? null
              : "Les pourcentages doivent être positifs et leur somme au plus 100."
          }
        />

        <div className="border-border space-y-3 border-t pt-5">
          <div>
            <Label>Prorata d'arrivée en cours de mois</Label>
            <p className="text-muted-foreground text-xs">
              Le mois est divisé en {segments.length} tranche(s) égales — un
              étudiant qui arrive dans une tranche paie le pourcentage
              correspondant du forfait.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            {segments.map((segment, index) => (
              <div key={index} className="space-y-1">
                <Label className="text-muted-foreground text-xs">
                  Tranche {index + 1} (%)
                </Label>
                <div className="flex items-center gap-1">
                  <Input
                    type="number"
                    min="0"
                    max="100"
                    value={segment}
                    onChange={(event) =>
                      setSegments((current) =>
                        current.map((s, i) =>
                          i === index ? event.target.value : s,
                        ),
                      )
                    }
                    className="w-20"
                  />
                  {segments.length > 1 && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setSegments(ladder(segments.length - 1))}
                    >
                      ×
                    </Button>
                  )}
                </div>
              </div>
            ))}
            <Button
              size="sm"
              variant="outline"
              onClick={() => setSegments(ladder(segments.length + 1))}
            >
              + Tranche
            </Button>
          </div>
          <Notice
            message={
              segmentsValid ? null : "Chaque tranche doit être entre 0 et 100%."
            }
          />
        </div>

        <div className="flex items-center gap-3">
          <Button
            onClick={save}
            disabled={!academy || !splitValid || !segmentsValid || busy}
          >
            {busy ? "…" : "Enregistrer"}
          </Button>
          {saved && <span className="text-success text-sm">Enregistré ✓</span>}
        </div>
      </div>

      <OwnerTeacher onError={setError} />
    </div>
  )
}

/** Le propriétaire enseigne aussi : le lier à sa fiche professeur fait
    additionner ses deux casquettes partout (profil, rapports, versements).
    Un seul champ — et un « ＋ » qui ouvre la vraie fiche professeur, la même
    que dans la page Professeurs (identité + arbre des compétences). */
function OwnerTeacher({ onError }: { onError: (message: string) => void }) {
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [choice, setChoice] = useState("")
  const [creating, setCreating] = useState(false)

  const reload = useCallback(
    (linkNewest = false) => {
      apiGet<Teacher[]>("/api/teachers")
        .then((rows) => {
          setTeachers(rows)
          const owner = rows.find((row) => row.is_owner === 1)
          if (linkNewest && !owner && rows.length > 0) {
            // La fiche vient d'être créée dans la modale : on la lie.
            const newest = rows.reduce((last, row) =>
              row.id > last.id ? row : last,
            )
            apiSend("PATCH", `/api/teachers/${newest.id}`, { is_owner: true })
              .then(() => reload())
              .catch((err: Error) => onError(err.message))
            return
          }
          setChoice(String(owner?.id ?? ""))
        })
        .catch(() => {})
    },
    [onError],
  )
  useEffect(() => reload(), [reload])

  const linked = teachers.find((row) => row.is_owner === 1)

  const link = (teacherId: number) => {
    setChoice(String(teacherId))
    apiSend("PATCH", `/api/teachers/${teacherId}`, { is_owner: true })
      .then(() => reload())
      .catch((err: Error) => onError(err.message))
  }

  return (
    <div className="surface-card space-y-3 p-6">
      <div>
        <Label>Le propriétaire enseigne aussi</Label>
        <p className="text-muted-foreground text-xs">
          {linked
            ? `${linked.name} cumule les deux casquettes : ses gains de professeur et ceux de l'académie s'additionnent dans son profil et les rapports.`
            : "Liez le propriétaire à sa fiche professeur pour additionner partout ce qu'il gagne comme professeur et comme académie."}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={choice} onValueChange={(value) => link(Number(value))}>
          <SelectTrigger className="w-56">
            <SelectValue placeholder="Choisir un professeur…" />
          </SelectTrigger>
          <SelectContent>
            {teachers.map((teacher) => (
              <SelectItem key={teacher.id} value={String(teacher.id)}>
                {teacher.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="icon"
          variant="outline"
          title="Créer sa fiche professeur"
          onClick={() => setCreating(true)}
        >
          <Plus className="size-4" />
        </Button>
      </div>

      <TeacherDialog
        open={creating}
        onOpenChange={setCreating}
        initial={null}
        onSaved={() => {
          setCreating(false)
          reload(true)
        }}
      />
    </div>
  )
}
