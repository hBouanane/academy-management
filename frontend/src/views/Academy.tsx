import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiGet, apiSend } from "@/lib/api"
import type { Academy as AcademyType } from "@/lib/api"

export function Academy() {
  const [academy, setAcademy] = useState<AcademyType | null>(null)
  const [name, setName] = useState("")
  const [venuePct, setVenuePct] = useState("")
  const [ownerPct, setOwnerPct] = useState("")
  const [segments, setSegments] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

      {error && (
        <p className="border-destructive/40 bg-destructive/10 text-destructive rounded-lg border p-3 text-sm">
          {error}
        </p>
      )}

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
        {!splitValid && (
          <p className="text-destructive text-sm">
            Les pourcentages doivent être positifs et leur somme au plus 100.
          </p>
        )}

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
                      onClick={() =>
                        setSegments((current) =>
                          current.filter((_, i) => i !== index),
                        )
                      }
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
              onClick={() => setSegments((current) => [...current, "33"])}
            >
              + Tranche
            </Button>
          </div>
          {!segmentsValid && (
            <p className="text-destructive text-sm">
              Chaque tranche doit être entre 0 et 100%.
            </p>
          )}
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
    </div>
  )
}
