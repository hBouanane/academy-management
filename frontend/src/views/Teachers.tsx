import { EntityManager } from "@/components/EntityManager"
import { MonthNav } from "@/components/MonthNav"
import { formatDH } from "@/lib/money"

type Props = { month: string; setMonth: (month: string) => void }

export function Teachers({ month, setMonth }: Props) {
  return (
    <EntityManager
      title="Professeurs"
      description="Ce que chaque professeur gagne le mois affiché — directement depuis le registre"
      endpoint="/api/teachers"
      query={`&month=${month}`}
      headerExtra={<MonthNav month={month} setMonth={setMonth} />}
      columns={[
        { key: "name", label: "Nom" },
        { key: "phone", label: "Téléphone" },
        {
          key: "subjects",
          label: "Matières",
          render: (row) => String(row.subjects ?? "—"),
        },
        {
          key: "earned_centimes",
          label: `Gagné (${month})`,
          render: (row) => (
            <span
              className={
                Number(row.earned_centimes) > 0 ? "text-success font-medium" : ""
              }
            >
              {formatDH(Number(row.earned_centimes ?? 0))}
            </span>
          ),
        },
      ]}
      fields={[
        { key: "name", label: "Nom", placeholder: "Ahmed Benali" },
        { key: "phone", label: "Téléphone", placeholder: "06…", optional: true },
      ]}
      toBody={(values) => ({ name: values.name, phone: values.phone ?? "" })}
    />
  )
}
