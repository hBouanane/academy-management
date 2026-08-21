import { useEffect, useState } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"

/**
 * Cutting up a list that keeps growing.
 *
 * An academy of six students fits on screen; three school years later it
 * has two hundred, and the page becomes a scroll where nothing can be
 * found. So we cut it into pages -- and the search keeps covering
 * EVERYTHING, not just the displayed page, otherwise searching would
 * stop being any use.
 */
export function usePagination<T>(items: T[], perPage = 25) {
  const [page, setPage] = useState(1)
  const pages = Math.max(1, Math.ceil(items.length / perPage))

  // Filtering shrinks the list: staying on page 4 would show emptiness.
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
    /** Below one page, the buttons would have nothing to do. */
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
  /** What is being counted, so the tally reads: « 132 élèves ». */
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
      {/* Say where you are within what: « 26–50 sur 132 » beats a page
          number on its own. */}
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
