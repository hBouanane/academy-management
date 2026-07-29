import { EntityManager } from "@/components/EntityManager"

export function Subjects() {
  return (
    <EntityManager
      title="Matières"
      description="Les matières enseignées dans l'académie"
      endpoint="/api/subjects"
      columns={[{ key: "name", label: "Nom" }]}
      fields={[{ key: "name", label: "Nom", placeholder: "Mathématiques" }]}
    />
  )
}
