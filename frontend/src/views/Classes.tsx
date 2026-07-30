import { useEffect, useState } from "react"
import { EntityManager } from "@/components/EntityManager"
import { MonthNav } from "@/components/MonthNav"
import { apiGet } from "@/lib/api"
import type { Level, Subject, Teacher } from "@/lib/api"

type Props = { month: string; setMonth: (month: string) => void }

export function Classes({ month, setMonth }: Props) {
  const [levels, setLevels] = useState<Level[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [teachers, setTeachers] = useState<Teacher[]>([])

  useEffect(() => {
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
    apiGet<Subject[]>("/api/subjects").then(setSubjects).catch(() => {})
    apiGet<Teacher[]>("/api/teachers").then(setTeachers).catch(() => {})
  }, [])

  const toOptions = (items: { id: number; name: string }[]): [string, string][] =>
    items.map((item) => [String(item.id), item.name])

  return (
    <EntityManager
      title="Classes"
      description="Une classe = une matière, un professeur, un niveau. Ajoutez une deuxième classe de la même matière quand l'académie grandit."
      endpoint="/api/classes"
      query={`&month=${month}`}
      headerExtra={<MonthNav month={month} setMonth={setMonth} />}
      columns={[
        { key: "subject_name", label: "Matière" },
        { key: "teacher_name", label: "Professeur" },
        { key: "level_name", label: "Niveau" },
        {
          key: "enrolled_count",
          label: `Inscrits (${month})`,
          render: (row) => String(row.enrolled_count ?? 0),
        },
      ]}
      fields={[
        { key: "level_id", label: "Niveau", type: "select", options: toOptions(levels) },
        {
          key: "subject_id",
          label: "Matière",
          type: "select",
          options: toOptions(subjects),
        },
        {
          key: "teacher_id",
          label: "Professeur",
          type: "select",
          options: toOptions(teachers),
        },
      ]}
      toBody={(values) => ({
        level_id: Number(values.level_id),
        subject_id: Number(values.subject_id),
        teacher_id: Number(values.teacher_id),
      })}
      fromRow={(row) => ({
        level_id: String(row.level_id),
        subject_id: String(row.subject_id),
        teacher_id: String(row.teacher_id),
      })}
    />
  )
}
