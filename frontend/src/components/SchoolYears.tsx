import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ConfirmButton } from "@/components/Confirm"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"
import type { SchoolYear } from "@/lib/api"

/** The name the two bounds carry: September 2020 to June 2021 is called
    « 2020 - 2021 ». A season fitting inside one calendar year has only
    one number to give. */
function nameOfSeason(start: string, end: string): string {
  if (!start || !end) return ""
  const first = start.slice(0, 4)
  const last = end.slice(0, 4)
  return first === last ? first : `${first} - ${last}`
}

/**
 * School years: the season, and the month it stops.
 *
 * Months scrolled on endlessly. But an academy does not live in months,
 * it lives in school years: it opens in September, closes in June, and
 * over the summer it does not count the same things.
 *
 * The end month is chosen, because nobody but him knows when HIS year
 * stops -- June here, July elsewhere.
 *
 * Closing a year archives the students. We do not presume they will
 * return: whoever comes back is re-enrolled as usual and finds his whole
 * history. What a family owes, by contrast, follows it -- money due does
 * not disappear because the calendar turned.
 */
export function SchoolYears({ onError }: { onError: (message: string) => void }) {
  const [years, setYears] = useState<SchoolYear[]>([])
  const [name, setName] = useState("")
  // Until he writes one himself, the name follows the months he picks.
  // The moment he writes one, we stop correcting it -- otherwise we would
  // erase, under his fingers, the name he has just typed.
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

  /** A bound moved. We reload the list: if the server refused (an end
      before the start), the field returns to its previous value. */
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
          {/* Nothing here is grave: the year placed at installation is a
              suggestion, not a decision. Its name and its bounds can be
              corrected, and if it serves no purpose it can be deleted. */}
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
