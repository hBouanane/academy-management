import { useEffect, useState } from "react"

import { apiGet } from "@/lib/api"
import type { Academy } from "@/lib/api"

/**
 * Son enseigne en haut de la barre — son nom, son logo.
 *
 * « Academy Management » était le nom de l'OUTIL. Lui ouvre
 * l'application pour voir SON académie, et quand un parent regarde
 * par-dessus son épaule, c'est son enseigne qui doit être là.
 *
 * Tant que rien n'est chargé on garde la pastille : un titre qui
 * apparaît puis change sous les yeux fait plus désordre qu'un rond qui
 * attend.
 */
export function AcademyMark() {
  const [name, setName] = useState<string | null>(null)
  const [logo, setLogo] = useState<string | null>(null)

  useEffect(() => {
    apiGet<Academy[]>("/api/academies")
      .then((all) => setName(all[0]?.name ?? null))
      .catch(() => setName(null))
    apiGet<{ logo: string | null }>("/api/settings/logo")
      .then((answer) => setLogo(answer.logo))
      .catch(() => setLogo(null))
  }, [])

  // L'événement est émis par la page Académie : le nom et le logo
  // changent là-bas, et la barre doit suivre sans qu'on relance tout.
  useEffect(() => {
    const again = () => {
      apiGet<Academy[]>("/api/academies")
        .then((all) => setName(all[0]?.name ?? null))
        .catch(() => {})
      apiGet<{ logo: string | null }>("/api/settings/logo")
        .then((answer) => setLogo(answer.logo))
        .catch(() => {})
    }
    window.addEventListener("academy-changed", again)
    return () => window.removeEventListener("academy-changed", again)
  }, [])

  return (
    <div className="mb-8 flex items-center gap-2 px-3">
      {logo ? (
        <img
          src={logo}
          alt=""
          className="size-6 shrink-0 rounded object-contain"
        />
      ) : (
        <span
          className="size-2.5 shrink-0 rounded-full"
          style={{
            background:
              "conic-gradient(var(--orb-mint), var(--orb-lavender), var(--orb-peach), var(--orb-mint))",
          }}
        />
      )}
      <h1 className="truncate text-sm font-semibold tracking-tight">
        {name ?? "Academy Management"}
      </h1>
    </div>
  )
}
