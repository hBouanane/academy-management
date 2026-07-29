import { EntityManager } from "@/components/EntityManager"
import { dhToCentimes, formatDH } from "@/lib/money"

export function Packages() {
  return (
    <EntityManager
      title="Forfaits"
      description="Le prix mensuel selon le nombre de matières choisies"
      endpoint="/api/packages"
      columns={[
        { key: "subject_count", label: "Matières" },
        {
          key: "monthly_price_centimes",
          label: "Prix mensuel",
          render: (row) => formatDH(Number(row.monthly_price_centimes)),
        },
      ]}
      fields={[
        { key: "subject_count", label: "Nb matières", type: "number", placeholder: "1" },
        { key: "price_dh", label: "Prix (DH)", type: "number", placeholder: "150" },
      ]}
      toBody={(values) => ({
        subject_count: Number(values.subject_count),
        monthly_price_centimes: dhToCentimes(values.price_dh),
      })}
      fromRow={(row) => ({
        subject_count: String(row.subject_count),
        price_dh: String(Number(row.monthly_price_centimes) / 100),
      })}
    />
  )
}
