import { EntityManager } from "@/components/EntityManager"

export function Motifs() {
  return (
    <EntityManager
      title="Motifs"
      description="Les raisons de réduction réutilisables — saisies une fois, proposées partout"
      endpoint="/api/motifs"
      columns={[{ key: "label", label: "Motif" }]}
      fields={[{ key: "label", label: "Motif", placeholder: "Situation familiale" }]}
    />
  )
}
