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

  const save = () => {
    if (!academy || !splitValid) return
    setError(null)
    setBusy(true)
    setSaved(false)
    apiSend("PATCH", `/api/academies/${academy.id}`, {
      name,
      venue_bp: Math.round(venue * 100),
      owner_bp: Math.round(owner * 100),
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
        <div className="flex items-center gap-3">
          <Button onClick={save} disabled={!academy || !splitValid || busy}>
            {busy ? "…" : "Enregistrer"}
          </Button>
          {saved && <span className="text-success text-sm">Enregistré ✓</span>}
        </div>
      </div>
    </div>
  )
}
