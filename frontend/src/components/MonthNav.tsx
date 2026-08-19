import { ChevronLeft, ChevronRight, Lock } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { currentMonth, previousMonth } from "@/lib/money"

export function nextMonth(month: string): string {
  const [year, monthNumber] = month.split("-").map(Number)
  const total = year * 12 + (monthNumber - 1) + 1
  return `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`
}

export const monthLabel = (month: string) =>
  new Date(`${month}-01T00:00:00`).toLocaleDateString("fr-FR", {
    month: "long",
    year: "numeric",
  })

export function MonthNav({
  month,
  setMonth,
}: {
  month: string
  setMonth: (month: string) => void
}) {
  const locked = month < currentMonth()
  return (
    <div className="surface-card flex items-center gap-1 p-1">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setMonth(previousMonth(month))}
        title="Mois précédent"
      >
        <ChevronLeft className="size-4" />
      </Button>
      <span className="min-w-36 text-center text-sm font-medium capitalize">
        {monthLabel(month)}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setMonth(nextMonth(month))}
        title="Mois suivant"
      >
        <ChevronRight className="size-4" />
      </Button>
      {locked && (
        <Badge variant="outline" className="ml-1 gap-1">
          <Lock className="size-3" /> Verrouillé
        </Badge>
      )}
    </div>
  )
}
