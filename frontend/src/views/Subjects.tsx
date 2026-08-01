import { useEffect, useState } from "react"
import { EntityManager } from "@/components/EntityManager"
import { apiGet } from "@/lib/api"
import type { Level } from "@/lib/api"

export function Subjects() {
  const [levels, setLevels] = useState<Level[]>([])

  useEffect(() => {
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
  }, [])

  return (
    <EntityManager
      title="Matières"
      description="Chaque matière appartient à son niveau — le même nom dans un autre niveau est une entrée à part"
      endpoint="/api/subjects"
      columns={[
        { key: "name", label: "Nom" },
        {
          key: "level_name",
          label: "Niveau",
          render: (row) => String(row.level_name ?? "Tous (ancien)"),
        },
        {
          key: "class_count",
          label: "Classes",
          render: (row) => String(row.class_count ?? 0),
        },
      ]}
      fields={[
        { key: "name", label: "Nom", placeholder: "Mathématiques" },
        {
          key: "level_id",
          label: "Niveau",
          type: "select",
          options: levels.map((level) => [String(level.id), level.name]),
        },
      ]}
      toBody={(values) => ({
        name: values.name,
        level_id: values.level_id ? Number(values.level_id) : null,
      })}
    />
  )
}
