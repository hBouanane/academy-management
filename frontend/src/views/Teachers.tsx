import { useState } from "react"
import { GraduationCap } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { CapabilityTree } from "@/components/CapabilityTree"
import { EntityManager } from "@/components/EntityManager"
import { MonthNav } from "@/components/MonthNav"
import { TeacherProfile } from "@/components/TeacherProfile"
import { formatDH } from "@/lib/money"

type Props = { month: string; setMonth: (month: string) => void }

export function Teachers({ month, setMonth }: Props) {
  const [profileId, setProfileId] = useState<number | null>(null)
  const [capabilityTarget, setCapabilityTarget] = useState<{
    id: number
    name: string
  } | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  return (
    <>
      <EntityManager
        title="Professeurs"
        description="Cliquez un professeur pour son profil complet — classes, gains, périodes"
        endpoint="/api/teachers"
        query={`&month=${month}`}
        refreshKey={refreshKey}
        headerExtra={<MonthNav month={month} setMonth={setMonth} />}
        onRowClick={(row) => setProfileId(row.id)}
        extraActions={(row) => (
          <Button
            size="sm"
            variant="ghost"
            title="Compétences — ce qu'il peut enseigner"
            onClick={() =>
              setCapabilityTarget({ id: row.id, name: String(row.name) })
            }
          >
            <GraduationCap className="size-4" />
          </Button>
        )}
        columns={[
          { key: "name", label: "Nom" },
          {
            key: "is_owner",
            label: "Rôle",
            render: (row) =>
              row.is_owner ? (
                <Badge variant="outline">Propriétaire</Badge>
              ) : (
                <span className="text-muted-foreground text-xs">—</span>
              ),
          },
          { key: "phone", label: "Téléphone" },
          {
            key: "created_at",
            label: "Depuis",
            render: (row) => (
              <span className="text-muted-foreground text-xs">
                {String(row.created_at ?? "").slice(0, 10) || "—"}
              </span>
            ),
          },
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
          {
            key: "is_owner",
            label: "Propriétaire de l'académie ?",
            type: "select",
            options: [
              ["0", "Non"],
              ["1", "Oui — ses parts se cumulent dans les rapports"],
            ],
            optional: true,
            editOnly: true,
          },
        ]}
        toBody={(values) => ({
          name: values.name,
          phone: values.phone ?? "",
          ...(values.is_owner === undefined || values.is_owner === ""
            ? {}
            : { is_owner: values.is_owner === "1" }),
        })}
      />

      <TeacherProfile
        teacherId={profileId}
        month={month}
        onClose={() => setProfileId(null)}
      />

      {capabilityTarget && (
        <CapabilityTree
          teacherId={capabilityTarget.id}
          teacherName={capabilityTarget.name}
          onClose={() => setCapabilityTarget(null)}
          onSaved={() => setRefreshKey((count) => count + 1)}
        />
      )}
    </>
  )
}
