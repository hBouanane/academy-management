import { useState } from "react"
import { Button } from "@/components/ui/button"
import { currentMonth } from "@/lib/money"
import { Dashboard } from "@/views/Dashboard"
import { Reports } from "@/views/Reports"
import { Settings } from "@/views/Settings"
import { Students } from "@/views/Students"

const VIEWS = [
  { key: "dashboard", label: "Tableau de bord" },
  { key: "students", label: "Étudiants" },
  { key: "reports", label: "Rapports" },
  { key: "settings", label: "Paramètres" },
] as const

type ViewKey = (typeof VIEWS)[number]["key"]

function App() {
  const [view, setView] = useState<ViewKey>("dashboard")
  const [month, setMonth] = useState(currentMonth())

  return (
    <div className="flex min-h-svh">
      <aside className="w-56 shrink-0 border-r p-4">
        <h1 className="mb-6 px-2 text-lg font-semibold tracking-tight">
          Académie
        </h1>
        <nav className="space-y-1">
          {VIEWS.map((item) => (
            <Button
              key={item.key}
              variant={view === item.key ? "secondary" : "ghost"}
              className="w-full justify-start"
              onClick={() => setView(item.key)}
            >
              {item.label}
            </Button>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-6">
        {view === "dashboard" && <Dashboard month={month} setMonth={setMonth} />}
        {view === "students" && <Students />}
        {view === "reports" && <Reports month={month} setMonth={setMonth} />}
        {view === "settings" && <Settings />}
      </main>
    </div>
  )
}

export default App
