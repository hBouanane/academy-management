import { useEffect, useState } from "react"
import type { ComponentType } from "react"
import {
  BarChart3,
  BookOpen,
  Building2,
  GraduationCap,
  LayoutDashboard,
  MessageCircle,
  Moon,
  Package,
  School,
  Lock as LockIcon,
  Sun,
  Tags,
  Users,
  Wallet,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { AcademyMark } from "@/components/AcademyMark"
import { LockScreen } from "@/components/LockScreen"
import { useLock } from "@/lib/useLock"
import { useTeacherRoute } from "@/lib/navigation"
import { TeacherPage } from "@/components/TeacherPage"
import { currentMonth } from "@/lib/money"
import { Academy } from "@/views/Academy"
import { Messages } from "@/views/Messages"
import { Classes } from "@/views/Classes"
import { Dashboard } from "@/views/Dashboard"
import { Motifs } from "@/views/Motifs"
import { Packages } from "@/views/Packages"
import { Payroll } from "@/views/Payroll"
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
      { key: "payroll", label: "Caisse", icon: Wallet },
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
      { key: "motifs", label: "Motifs", icon: Tags },
    ],
  },
  {
    label: "Configuration",
    items: [
      { key: "messages", label: "Messages", icon: MessageCircle },
      { key: "academy", label: "Académie", icon: Building2 },
    ],
  },
]

function useTheme() {
  const [dark, setDark] = useState(
    () => localStorage.getItem("theme") !== "light",
  )
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
    localStorage.setItem("theme", dark ? "dark" : "light")
  }, [dark])
  return { dark, toggle: () => setDark((current) => !current) }
}

function App() {
  const [view, setView] = useState("dashboard")
  const [month, setMonth] = useState(currentMonth())
  const { dark, toggle } = useTheme()
  const lock = useLock()
  // A teacher's profile is a page, not a window: it takes the place of
  // the content and leaves the sidebar where it is.
  const teacher = useTeacherRoute()

  // Until the lock has answered we show nothing: flashing the academy
  // for half a second before hiding it would be worse than anything.
  if (lock.state === null) return null
  if (!lock.open) return <LockScreen onOpened={lock.opened} />

  return (
    <div className="flex min-h-svh">
      <aside className="border-sidebar-border bg-sidebar sticky top-0 flex h-svh w-60 shrink-0 flex-col self-start overflow-y-auto border-r px-3 py-5">
        <AcademyMark />
        <nav className="flex-1 space-y-6">
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
                      onClick={() => {
                        teacher.close()
                        setView(item.key)
                      }}
                      className={`flex w-full items-center gap-2.5 rounded-full px-3 py-1.5 text-sm transition-colors duration-150 ${
                        active
                          ? "bg-sidebar-primary text-sidebar-primary-foreground"
                          : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                      }`}
                    >
                      <Icon className="size-4" />
                      {item.label}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>
        <Button
          variant="ghost"
          size="sm"
          onClick={toggle}
          className="justify-start gap-2.5 rounded-full px-3"
          title={dark ? "Passer en mode clair" : "Passer en mode sombre"}
        >
          {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          {dark ? "Mode clair" : "Mode sombre"}
        </Button>
        {/* Stepping away from the desk for a minute should not mean
            waiting out the timer. */}
        {lock.state.configured && (
          <Button
            variant="ghost"
            size="sm"
            onClick={lock.close}
            className="justify-start gap-2.5 rounded-full px-3"
            title="Verrouiller maintenant"
          >
            <LockIcon className="size-4" />
            Verrouiller
          </Button>
        )}
      </aside>
      <main
        className="min-w-0 flex-1 px-8 py-6"
        key={teacher.teacherId === null ? view : `teacher-${teacher.teacherId}`}
      >
        {teacher.teacherId !== null && (
          <TeacherPage
            teacherId={teacher.teacherId}
            month={month}
            setMonth={setMonth}
            onClose={teacher.close}
          />
        )}
        {teacher.teacherId === null && (
          <>
            {view === "dashboard" && (
              <Dashboard month={month} setMonth={setMonth} />
            )}
            {view === "reports" && (
              <Reports month={month} setMonth={setMonth} />
            )}
            {/* The till has its own month: the elapsed one, not the current. */}
            {view === "payroll" && <Payroll />}
            {view === "students" && (
              <Students month={month} setMonth={setMonth} />
            )}
            {view === "teachers" && (
              <Teachers month={month} setMonth={setMonth} />
            )}
            {view === "subjects" && <Subjects />}
            {view === "classes" && (
              <Classes month={month} setMonth={setMonth} />
            )}
            {view === "packages" && <Packages />}
            {view === "motifs" && <Motifs />}
            {view === "messages" && <Messages />}
        {view === "academy" && <Academy />}
          </>
        )}
      </main>
    </div>
  )
}

export default App
