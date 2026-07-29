import { useEffect, useState } from "react"
import { EntityManager } from "@/components/EntityManager"
import { apiGet } from "@/lib/api"
import type { Level } from "@/lib/api"
import { dhToCentimes, formatDH } from "@/lib/money"

export function Packages() {
  const [levels, setLevels] = useState<Level[]>([])
  useEffect(() => {
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
  }, [])

  return (
    <EntityManager
      title="Forfaits"
      description="Le prix mensuel par niveau et nombre de matières — un forfait ne peut pas dépasser les matières enseignées à son niveau"
      endpoint="/api/packages"
      columns={[
        {
          key: "level_name",
          label: "Niveau",
          render: (row) => String(row.level_name ?? "Tous niveaux"),
        },
        { key: "subject_count", label: "Matières" },
        {
          key: "monthly_price_centimes",
          label: "Prix mensuel",
          render: (row) => formatDH(Number(row.monthly_price_centimes)),
        },
      ]}
      fields={[
        {
          key: "level_id",
          label: "Niveau",
          type: "select",
          options: levels.map((level) => [String(level.id), level.name]),
        },
        { key: "subject_count", label: "Nb matières", type: "number", placeholder: "1" },
        { key: "price_dh", label: "Prix (DH)", type: "number", placeholder: "150" },
      ]}
      toBody={(values) => ({
        level_id: values.level_id ? Number(values.level_id) : null,
        subject_count: Number(values.subject_count),
        monthly_price_centimes: dhToCentimes(values.price_dh),
      })}
      fromRow={(row) => ({
        level_id: row.level_id ? String(row.level_id) : "",
        subject_count: String(row.subject_count),
        price_dh: String(Number(row.monthly_price_centimes) / 100),
      })}
    />
  )
}
