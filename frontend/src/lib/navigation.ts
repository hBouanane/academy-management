import { useEffect, useState } from "react"

/**
 * Going to see a teacher, from anywhere.
 *
 * The application has no router: screens are chosen in the sidebar. A
 * teacher's profile, though, opens from three different places -- the
 * till, the classes, the teacher list. Threading a function down from App
 * to each button would cross four components that have no interest in it.
 *
 * An event is enough: whoever wants to open one shouts, App hears it.
 */
const EVENT = "academy-open-teacher"

export function openTeacher(teacherId: number) {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: teacherId }))
}

/** Le professeur affiché en pleine page, ou rien. */
export function useTeacherRoute() {
  const [teacherId, setTeacherId] = useState<number | null>(null)

  useEffect(() => {
    const listen = (event: Event) =>
      setTeacherId((event as CustomEvent<number>).detail)
    window.addEventListener(EVENT, listen)
    return () => window.removeEventListener(EVENT, listen)
  }, [])

  return { teacherId, close: () => setTeacherId(null) }
}

const VIEW_EVENT = "academy-open-view"

/** Jump to a section from anywhere -- same reasoning as openTeacher: the
    button that wants it sits four components away from the state. */
export function openView(view: string) {
  window.dispatchEvent(new CustomEvent(VIEW_EVENT, { detail: view }))
}

export function useViewRoute(setView: (view: string) => void) {
  useEffect(() => {
    const listen = (event: Event) => setView((event as CustomEvent<string>).detail)
    window.addEventListener(VIEW_EVENT, listen)
    return () => window.removeEventListener(VIEW_EVENT, listen)
  }, [setView])
}
