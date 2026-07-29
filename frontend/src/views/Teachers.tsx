import { EntityManager } from "@/components/EntityManager"

export function Teachers() {
  return (
    <EntityManager
      title="Professeurs"
      description="Chaque professeur reçoit sa part par matière enseignée"
      endpoint="/api/teachers"
      columns={[
        { key: "name", label: "Nom" },
        { key: "phone", label: "Téléphone" },
      ]}
      fields={[
        { key: "name", label: "Nom", placeholder: "Ahmed Benali" },
        { key: "phone", label: "Téléphone", placeholder: "06…", optional: true },
      ]}
      toBody={(values) => ({ name: values.name, phone: values.phone ?? "" })}
    />
  )
}
