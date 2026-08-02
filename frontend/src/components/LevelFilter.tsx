// Niveau → année filter chips: one click shows « Collège · 2ème année »
// without giving up the flat, searchable table underneath.

import type { Level } from "@/lib/api"
import { teachingAnnees } from "@/lib/levels"

export type LevelFilterValue = { levelId: number | null; annee: number | null }

export const matchesLevelFilter = (
  filter: LevelFilterValue,
  row: { level_id: number; annee: number | null },
): boolean => {
  if (filter.levelId === null) return true
  if (row.level_id !== filter.levelId) return false
  return filter.annee === null || row.annee === filter.annee
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs transition-colors ${
        active
          ? "border-transparent bg-primary text-primary-foreground"
          : "border-border text-muted-foreground hover:border-foreground/40"
      }`}
    >
      {children}
    </button>
  )
}

export function LevelFilter({
  levels,
  value,
  onChange,
}: {
  levels: Level[]
  value: LevelFilterValue
  onChange: (value: LevelFilterValue) => void
}) {
  const level = levels.find((entry) => entry.id === value.levelId)
  const annees = level ? teachingAnnees(level) : []
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1.5">
        <Chip
          active={value.levelId === null}
          onClick={() => onChange({ levelId: null, annee: null })}
        >
          Tous
        </Chip>
        {levels.map((entry) => (
          <Chip
            key={entry.id}
            active={value.levelId === entry.id}
            onClick={() => onChange({ levelId: entry.id, annee: null })}
          >
            {entry.name}
          </Chip>
        ))}
      </div>
      {annees.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <Chip
            active={value.annee === null}
            onClick={() => onChange({ ...value, annee: null })}
          >
            Toutes les années
          </Chip>
          {annees.map(([annee, label]) => (
            <Chip
              key={annee}
              active={value.annee === Number(annee)}
              onClick={() => onChange({ ...value, annee: Number(annee) })}
            >
              {label}
            </Chip>
          ))}
        </div>
      )}
    </div>
  )
}
