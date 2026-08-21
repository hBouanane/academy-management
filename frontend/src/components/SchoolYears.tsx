import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ConfirmButton } from "@/components/Confirm"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"
import type { SchoolYear } from "@/lib/api"

/** Le nom que portent les deux bornes : septembre 2020 → juin 2021 se
    dit « 2020 - 2021 ». Une saison qui tient dans une seule année civile
    n'a qu'un nombre à donner. */
function nameOfSeason(start: string, end: string): string {
  if (!start || !end) return ""
  const first = start.slice(0, 4)
  const last = end.slice(0, 4)
  return first === last ? first : `${first} - ${last}`
}

/**
 * Les années scolaires : la saison, et le mois où elle s'arrête.
 *
 * Les mois défilaient sans fin. Or une académie ne vit pas en mois,
 * elle vit en rentrées : on ouvre en septembre, on ferme en juin, et
 * l'été on ne compte pas les mêmes choses.
 *
 * Le mois de fin se choisit, parce que personne d'autre que lui ne sait
 * quand SON année s'arrête — ici juin, ailleurs juillet.
 *
 * Clore une année archive les élèves. On ne présume pas qu'ils
 * reviendront : celui qui revient est réinscrit comme d'habitude et
 * retrouve son histoire entière. Ce qu'une famille doit, en revanche,
 * la suit — l'argent dû ne s'efface pas parce que le calendrier a
 * tourné.
 */
export function SchoolYears({ onError }: { onError: (message: string) => void }) {
  const [years, setYears] = useState<SchoolYear[]>([])
  const [name, setName] = useState("")
  // Tant qu'il n'a rien écrit lui-même, le nom suit les mois qu'il
  // choisit. Dès qu'il en écrit un, on cesse de le corriger — sinon on
  // effacerait sous ses doigts le nom qu'il vient de taper.
  const [named, setNamed] = useState(false)
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const toast = useToast()

  const shownName = named ? name : nameOfSeason(start, end)

  const load = useCallback(() => {
    apiGet<SchoolYear[]>("/api/school-years")
      .then(setYears)
      .catch((err: Error) => onError(err.message))
  }, [onError])

  useEffect(load, [load])

  const add = async () => {
    if (!shownName.trim() || !start || !end) return
    await apiSend("POST", "/api/school-years", {
      name: shownName.trim(),
      start_month: start,
      end_month: end,
    })
      .then(() => {
        setName("")
        setNamed(false)
        setStart("")
        setEnd("")
        load()
      })
      .catch((err: Error) => onError(err.message))
  }

  /** Une borne déplacée. On repart de la liste : si le serveur a refusé
      (une fin avant le début), le champ retrouve sa valeur d'avant. */
  const moveEdge = async (
    year: SchoolYear,
    edge: "start_month" | "end_month",
    month: string,
  ) => {
    if (!month || month === year[edge]) return
    await apiSend("PATCH", `/api/school-years/${year.id}`, { [edge]: month })
      .then(load)
      .catch((err: Error) => {
        onError(err.message)
        load()
      })
  }

  const rename = async (year: SchoolYear, name: string) => {
    if (!name.trim() || name === year.name) return
    await apiSend("PATCH", `/api/school-years/${year.id}`, { name: name.trim() })
      .then(load)
      .catch((err: Error) => {
        onError(err.message)
        load()
      })
  }

  const remove = async (year: SchoolYear) => {
    await apiSend("DELETE", `/api/school-years/${year.id}`)
      .then(() => {
        toast(`${year.name} supprimée`)
        load()
      })
      .catch((err: Error) => onError(err.message))
  }

  const close = async (year: SchoolYear) => {
    await apiSend("POST", `/api/school-years/${year.id}/close`, {})
      .then(() => {
        toast(`${year.name} est close — les élèves sont archivés`)
        load()
      })
      .catch((err: Error) => onError(err.message))
  }

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label>Années scolaires</Label>
        <p className="text-muted-foreground text-xs">
          Une saison va d'un mois à un autre — c'est vous qui dites lequel.
          La clôture archive les élèves : on ne suppose pas qu'ils
          reviendront, et celui qui revient se réinscrit comme d'habitude.
          Ce qu'une famille doit reste dû.
        </p>
      </div>

      {years.length === 0 && (
        <p className="text-muted-foreground text-sm">
          Aucune année pour l'instant.
        </p>
      )}

      {years.map((year) => (
        <div
          key={year.id}
          className="border-border flex flex-wrap items-center gap-3 rounded-md border px-3 py-2"
        >
          {/* Rien n'est grave ici : l'année posée à l'installation est
              une proposition, pas une décision. Son nom et ses bornes se
              corrigent, et si elle ne sert à rien elle s'efface. */}
          <Input
            className="h-8 w-40 font-medium"
            defaultValue={year.name}
            disabled={Boolean(year.closed_at)}
            onBlur={(event) => rename(year, event.target.value)}
          />
          <label className="text-muted-foreground flex items-center gap-1.5 text-sm">
            de
            <Input
              type="month"
              className="h-8 w-36"
              defaultValue={year.start_month}
              disabled={Boolean(year.closed_at)}
              onBlur={(event) => moveEdge(year, "start_month", event.target.value)}
            />
          </label>
          <label className="text-muted-foreground flex items-center gap-1.5 text-sm">
            jusqu'à
            <Input
              type="month"
              className="h-8 w-36"
              defaultValue={year.end_month}
              disabled={Boolean(year.closed_at)}
              onBlur={(event) => moveEdge(year, "end_month", event.target.value)}
            />
          </label>
          <span className="flex-1" />
          {year.closed_at ? (
            <span className="text-muted-foreground text-xs">
              close le {year.closed_at.slice(0, 10)}
            </span>
          ) : (
            <ConfirmButton
              size="sm"
              variant="outline"
              confirmLabel="Clore l'année"
              description="Les élèves seront archivés — on ne suppose pas qu'ils reviendront. Celui qui revient se réinscrit et retrouve son histoire. Ce qu'une famille doit reste dû."
              onConfirm={() => close(year)}
            >
              Clore l'année
            </ConfirmButton>
          )}
          <ConfirmButton
            size="sm"
            variant="ghost"
            title="Supprimer cette année"
            confirmLabel="Supprimer"
            description="Une année n'est qu'une période : l'effacer ne défait aucun paiement et ne réveille aucun élève archivé. Vous perdrez seulement son bilan de saison."
            onConfirm={() => remove(year)}
          >
            <Trash2 className="size-4" />
          </ConfirmButton>
        </div>
      ))}

      <div className="flex flex-wrap items-end gap-2">
        <div>
          <Label htmlFor="annee-nom" className="text-xs">
            Nom
          </Label>
          <Input
            id="annee-nom"
            className="h-8 w-40"
            placeholder="2026 - 2027"
            value={shownName}
            onChange={(event) => {
              setNamed(true)
              setName(event.target.value)
            }}
          />
        </div>
        <div>
          <Label htmlFor="annee-debut" className="text-xs">
            Premier mois
          </Label>
          <Input
            id="annee-debut"
            type="month"
            className="h-8 w-36"
            value={start}
            onChange={(event) => setStart(event.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="annee-fin" className="text-xs">
            Dernier mois
          </Label>
          <Input
            id="annee-fin"
            type="month"
            className="h-8 w-36"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
          />
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={add}
          disabled={!shownName.trim() || !start || !end}
        >
          <Plus className="size-4" />
          Ajouter
        </Button>
      </div>
    </div>
  )
}
