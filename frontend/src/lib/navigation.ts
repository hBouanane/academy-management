import { useEffect, useState } from "react"

/**
 * Aller voir un professeur, depuis n'importe où.
 *
 * L'application n'a pas de routeur : les écrans se choisissent dans la
 * barre de gauche. Le profil d'un professeur, lui, s'ouvre depuis trois
 * endroits différents — la caisse, les classes, la liste des
 * professeurs. Faire descendre une fonction depuis App jusqu'à chaque
 * bouton traverserait quatre composants qui n'en ont que faire.
 *
 * Un évènement suffit : celui qui veut ouvrir le crie, App l'entend.
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
