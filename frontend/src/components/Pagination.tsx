import { useEffect, useState } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"

/**
 * Découper une liste qui grossit.
 *
 * Une académie de six élèves tient à l'écran ; trois rentrées plus tard
 * elle en a deux cents, et la page devient un rouleau où l'on ne trouve
 * plus rien. On coupe donc en pages — et la recherche continue de
 * porter sur TOUT, pas seulement sur la page affichée, sinon chercher
 * ne servirait plus à rien.
 */
export function usePagination<T>(items: T[], perPage = 25) {
  const [page, setPage] = useState(1)
  const pages = Math.max(1, Math.ceil(items.length / perPage))

  // Filtrer réduit la liste : rester page 4 afficherait du vide.
  useEffect(() => {
    setPage((current) => Math.min(current, pages))
  }, [pages])

  const from = (page - 1) * perPage
  return {
    page,
    pages,
    setPage,
    total: items.length,
    from,
    visible: items.slice(from, from + perPage),
    /** En dessous d'une page, les boutons n'auraient rien à faire. */
    needed: items.length > perPage,
  }
}

type Props = {
  page: number
  pages: number
  total: number
  from: number
  shown: number
  setPage: (page: number) => void
  /** Ce qu'on compte, pour que le décompte se lise : « 132 élèves ». */
  noun?: string
  className?: string
}

export function Pagination({
  page,
  pages,
  total,
  from,
  shown,
  setPage,
  noun = "lignes",
  className = "",
}: Props) {
  if (pages <= 1) return null
  return (
    <div
      className={`text-muted-foreground flex flex-wrap items-center justify-between gap-2 pt-3 text-sm ${className}`}
    >
      {/* Dire où l'on est dans quoi : « 26–50 sur 132 » vaut mieux
          qu'un numéro de page seul. */}
      <span>
        {from + 1}–{from + shown} sur {total} {noun}
      </span>
      <div className="flex items-center gap-1">
        <Button
          size="sm"
          variant="outline"
          disabled={page === 1}
          onClick={() => setPage(page - 1)}
          title="Page précédente"
        >
          <ChevronLeft className="size-4" />
        </Button>
        <span className="px-1 text-xs">
          {page} / {pages}
        </span>
        <Button
          size="sm"
          variant="outline"
          disabled={page === pages}
          onClick={() => setPage(page + 1)}
          title="Page suivante"
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  )
}
