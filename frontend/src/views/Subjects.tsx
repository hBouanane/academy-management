import { EntityManager } from "@/components/EntityManager"

export function Subjects() {
  return (
    <EntityManager
      title="Matières"
      description="Les matières enseignées, et où elles le sont"
      endpoint="/api/subjects"
      columns={[
        { key: "name", label: "Nom" },
        {
          key: "levels",
          label: "Niveaux",
          render: (row) => String(row.levels ?? "Aucune classe"),
        },
        {
          key: "class_count",
          label: "Classes",
          render: (row) => String(row.class_count ?? 0),
        },
      ]}
      fields={[{ key: "name", label: "Nom", placeholder: "Mathématiques" }]}
    />
  )
}
