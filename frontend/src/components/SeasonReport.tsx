import { useEffect, useState } from "react"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { apiGet } from "@/lib/api"
import type { SchoolYear, SeasonReport as Season } from "@/lib/api"
import { formatDH } from "@/lib/money"

/**
 * Le bilan d'une saison entière, pas d'un mois.
 *
 * Un mois isolé ne dit pas si l'année a été bonne : la rentrée est
 * grasse, le printemps maigre, et juillet ne compte pas. Additionner
 * les mois de la saison est la seule façon de comparer une année à la
 * précédente.
 *
 * On y lit deux choses : ce qui est entré et la part de chacun, puis ce
 * que chaque professeur a gagné sur toute l'année.
 */
export function SeasonReport({
  onError,
}: {
  onError: (message: string) => void
}) {
  const [years, setYears] = useState<SchoolYear[]>([])
  const [chosen, setChosen] = useState<number | null>(null)
  const [report, setReport] = useState<Season | null>(null)

  useEffect(() => {
    apiGet<SchoolYear[]>("/api/school-years")
      .then((listed) => {
        setYears(listed)
        // La plus récente d'abord : c'est celle qu'il regarde.
        if (listed.length > 0) setChosen((current) => current ?? listed[0].id)
      })
      .catch((err: Error) => onError(err.message))
  }, [onError])

  useEffect(() => {
    if (chosen === null) return
    apiGet<Season>(`/api/reports/school-year/${chosen}`)
      .then(setReport)
      .catch((err: Error) => onError(err.message))
  }, [chosen, onError])

  if (years.length === 0) return null

  const peak = Math.max(...(report?.teachers ?? []).map((t) => t.earned), 1)

  return (
    <div className="surface-card p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-muted-foreground text-sm">
            Bilan de l'année scolaire
          </p>
          {report && (
            <p className="text-muted-foreground text-xs">
              {report.start_month} → {report.end_month} · {report.months} mois
            </p>
          )}
        </div>
        <Select
          value={chosen === null ? undefined : String(chosen)}
          onValueChange={(value) => setChosen(Number(value))}
        >
          <SelectTrigger className="h-8 w-44">
            <SelectValue placeholder="Choisir l'année" />
          </SelectTrigger>
          <SelectContent>
            {years.map((year) => (
              <SelectItem key={year.id} value={String(year.id)}>
                {year.name}
                {year.closed_at ? " (close)" : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {report && (
        <div className="space-y-4">
          <div>
            <p className="text-muted-foreground text-xs">
              Encaissé sur l'année
            </p>
            <p className="text-2xl font-medium tracking-tight">
              {formatDH(report.cash_in)}
            </p>
          </div>

          {report.totals.length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1.5 text-xs">
                La part de chacun
              </p>
              <div className="space-y-1">
                {report.totals.map((total) => (
                  <div
                    key={`${total.kind}-${total.ref_id}`}
                    className="flex items-center justify-between text-sm"
                  >
                    <span>{total.name}</span>
                    <span className="font-medium">{formatDH(total.total)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {report.teachers.length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1.5 text-xs">
                Chaque professeur sur l'année
              </p>
              <div className="space-y-1">
                {report.teachers.map((teacher) => (
                  <div
                    key={teacher.teacher_id}
                    className="flex items-center gap-2"
                  >
                    <span className="w-32 shrink-0 truncate text-sm">
                      {teacher.name}
                    </span>
                    <span className="bg-muted h-1.5 flex-1 overflow-hidden rounded-full">
                      <span
                        className="bg-success block h-full rounded-full"
                        style={{ width: `${(teacher.earned / peak) * 100}%` }}
                      />
                    </span>
                    <span className="w-24 shrink-0 text-right text-sm font-medium">
                      {formatDH(teacher.earned)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {report.cash_in === 0 && (
            <p className="text-muted-foreground text-sm">
              Rien d'encaissé sur cette saison.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
