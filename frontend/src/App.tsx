import { useState } from "react"
import type { ComponentType } from "react"
import {
  BarChart3,
  BookOpen,
  Building2,
  GraduationCap,
  LayoutDashboard,
  Package,
  School,
  Users,
} from "lucide-react"
import { currentMonth } from "@/lib/money"
import { Academy } from "@/views/Academy"
import { Classes } from "@/views/Classes"
import { Dashboard } from "@/views/Dashboard"
import { Packages } from "@/views/Packages"
import { Reports } from "@/views/Reports"
import { Students } from "@/views/Students"
import { Subjects } from "@/views/Subjects"
import { Teachers } from "@/views/Teachers"

type IconType = ComponentType<{ className?: string }>

const SECTIONS: {
  label: string
  items: { key: string; label: string; icon: IconType }[]
}[] = [
  {
    label: "Pilotage",
    items: [
      { key: "dashboard", label: "Tableau de bord", icon: LayoutDashboard },
      { key: "reports", label: "Rapports", icon: BarChart3 },
    ],
  },
  {
    label: "Gestion",
    items: [
      { key: "students", label: "Étudiants", icon: Users },
      { key: "teachers", label: "Professeurs", icon: GraduationCap },
      { key: "subjects", label: "Matières", icon: BookOpen },
      { key: "classes", label: "Classes", icon: School },
      { key: "packages", label: "Forfaits", icon: Package },
    ],
  },
  {
    label: "Configuration",
    items: [{ key: "academy", label: "Académie", icon: Building2 }],
  },
]

function App() {
  const [view, setView] = useState("dashboard")
  const [month, setMonth] = useState(currentMonth())

  return (
    <div className="flex min-h-svh">
      <aside className="border-sidebar-border bg-sidebar w-60 shrink-0 border-r px-3 py-5">
        <div className="mb-8 flex items-center gap-2 px-3">
          <span className="bg-primary size-2.5 rounded-full" />
          <h1 className="text-sm font-semibold tracking-tight">
            Academy Management
          </h1>
        </div>
        <nav className="space-y-6">
          {SECTIONS.map((section) => (
            <div key={section.label}>
              <p className="text-muted-foreground/70 mb-1.5 px-3 text-[11px] font-medium tracking-widest uppercase">
                {section.label}
              </p>
              <div className="space-y-0.5">
                {section.items.map((item) => {
                  const active = view === item.key
                  const Icon = item.icon
                  return (
                    <button
                      key={item.key}
                      onClick={() => setView(item.key)}
                      className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-1.5 text-sm transition-colors duration-150 ${
                        active
                          ? "bg-sidebar-accent text-sidebar-accent-foreground"
                          : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
                      }`}
                    >
                      <Icon
                        className={`size-4 ${active ? "text-primary" : "text-muted-foreground"}`}
                      />
                      {item.label}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 px-8 py-6" key={view}>
        {view === "dashboard" && <Dashboard month={month} setMonth={setMonth} />}
        {view === "reports" && <Reports month={month} setMonth={setMonth} />}
        {view === "students" && <Students month={month} />}
        {view === "teachers" && <Teachers />}
        {view === "subjects" && <Subjects />}
        {view === "classes" && <Classes />}
        {view === "packages" && <Packages />}
        {view === "academy" && <Academy />}
      </main>
    </div>
  )
}

export default App
