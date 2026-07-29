import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { apiGet } from "@/lib/api"
import type { ArrearsEntry, BeneficiaryTotal, MonthlyReport } from "@/lib/api"
import { formatDH } from "@/lib/money"

const KIND_LABEL: Record<BeneficiaryTotal["kind"], string> = {
  teacher: "Professeur",
  owner: "Propriétaire",
  venue: "Salle",
}

type Props = { month: string; setMonth: (month: string) => void }

export function Reports({ month, setMonth }: Props) {
  const [report, setReport] = useState<MonthlyReport | null>(null)
  const [owing, setOwing] = useState<ArrearsEntry[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    apiGet<MonthlyReport>(`/api/reports/monthly?month=${month}`)
      .then(setReport)
      .catch((err: Error) => setError(err.message))
    apiGet<ArrearsEntry[]>(`/api/reports/arrears?up_to_month=${month}`)
      .then(setOwing)
      .catch(() => setOwing([]))
  }, [month])

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Rapports</h2>
          <p className="text-muted-foreground text-sm">
            Qui reçoit quoi — calculé depuis le registre, jamais recalculé
          </p>
        </div>
        <Input
          type="month"
          value={month}
          onChange={(event) => setMonth(event.target.value)}
          className="w-44"
        />
      </header>

      {error && <p className="text-destructive text-sm">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Répartition du mois {month}</CardTitle>
          <CardDescription>
            Encaissé : {report ? formatDH(report.cash_in) : "—"}
          </CardDescription>
        </CardHeader>
        <div className="px-6 pb-6">
          <TotalsTable totals={report?.totals ?? []} />
        </div>
      </Card>

      {report?.by_level.map((level) => (
        <Card key={level.level_id}>
          <CardHeader>
            <CardTitle>{level.level_name}</CardTitle>
          </CardHeader>
          <div className="px-6 pb-6">
            <TotalsTable totals={level.totals} />
          </div>
        </Card>
      ))}

      <Card>
        <CardHeader>
          <CardTitle>Impayés (jusqu'à {month})</CardTitle>
          <CardDescription>
            Étudiants qui doivent encore de l'argent
          </CardDescription>
        </CardHeader>
        <div className="px-6 pb-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Étudiant</TableHead>
                <TableHead>Niveau</TableHead>
                <TableHead>Mois dus</TableHead>
                <TableHead className="text-right">Total dû</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {owing.map((entry) => (
                <TableRow key={entry.student_id}>
                  <TableCell className="font-medium">
                    {entry.student_name}
                  </TableCell>
                  <TableCell>{entry.level_name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {entry.items
                      .map((item) => `${item.month} (${formatDH(item.owed)})`)
                      .join(", ")}
                  </TableCell>
                  <TableCell className="text-right font-medium">
                    {formatDH(entry.total_owed)}
                  </TableCell>
                </TableRow>
              ))}
              {owing.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={4}
                    className="text-muted-foreground text-center"
                  >
                    Personne ne doit rien 🎉
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  )
}

function TotalsTable({ totals }: { totals: BeneficiaryTotal[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Bénéficiaire</TableHead>
          <TableHead>Rôle</TableHead>
          <TableHead className="text-right">Montant</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {totals.map((total) => (
          <TableRow key={`${total.kind}-${total.ref_id}`}>
            <TableCell className="font-medium">{total.name}</TableCell>
            <TableCell>
              <Badge variant="outline">{KIND_LABEL[total.kind]}</Badge>
            </TableCell>
            <TableCell className="text-right">
              {formatDH(total.total)}
            </TableCell>
          </TableRow>
        ))}
        {totals.length === 0 && (
          <TableRow>
            <TableCell colSpan={3} className="text-muted-foreground text-center">
              Aucun paiement ce mois
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  )
}
