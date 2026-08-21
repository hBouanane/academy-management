import { useEffect, useState } from "react"

import { apiGet } from "@/lib/api"
import type { Academy } from "@/lib/api"

/**
 * His sign at the top of the sidebar -- his name, his logo.
 *
 * « Academy Management » was the name of the TOOL. He opens the
 * application to see HIS academy, and when a parent looks over his
 * shoulder it is his own sign that should be there.
 *
 * While nothing is loaded we keep the dot: a title that appears and then
 * changes under the reader's eyes is messier than a circle that waits.
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

  // The event is emitted by the Academy page: the name and the logo
  // change over there, and the sidebar must follow without a reload.
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
