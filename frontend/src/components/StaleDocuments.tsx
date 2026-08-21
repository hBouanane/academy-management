import { useCallback, useEffect, useState } from "react"
import { FileWarning, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"
import type { StaleDocument } from "@/lib/api"
import { monthLabel } from "@/components/MonthNav"

/**
 * The papers the figures have overtaken.
 *
 * The case that matters is a PAST month: a September impayé comes in
 * during November, and the payslip printed in September becomes wrong
 * without anything saying so. Here, we say so -- and we name the
 * document, not the month: « la fiche de Moulay Idris », not « septembre
 * a changé », otherwise the warning would cover ten files of which nine
 * are still correct.
 */
export function StaleDocuments({ month }: { month?: string }) {
  const [items, setItems] = useState<StaleDocument[]>([])
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  const reload = useCallback(
    () =>
      apiGet<StaleDocument[]>(
        month ? `/api/documents/stale?month=${month}` : "/api/documents/stale",
      )
        .then(setItems)
        .catch(() => setItems([])),
    [month],
  )
  useEffect(() => {
    void reload()
  }, [reload])

  if (items.length === 0) return null

  const refileAll = () => {
    setBusy(true)
    Promise.all(
      items.map((item) =>
        apiSend("POST", "/api/documents/file", {
          kind: item.kind,
          month: item.month,
          ref_id: item.ref_id,
        }),
      ),
    )
      .then(() => toast(`${items.length} document(s) regénéré(s)`))
      .catch((err: Error) => toast(err.message, "error"))
      .finally(() => {
        setBusy(false)
        void reload()
      })
  }

  return (
    <div className="border-amber-500/40 bg-amber-500/10 space-y-2 rounded-xl border p-3">
      <p className="flex items-center gap-2 text-sm font-medium text-amber-600">
        <FileWarning className="size-4 shrink-0" />
        {items.length} document(s) à regénérer — les chiffres ont bougé
        depuis
      </p>
      <ul className="space-y-1 text-sm text-amber-600/90">
        {items.map((item) => (
          <li key={`${item.kind}-${item.month}-${item.ref_id}`}>
            {item.label} · {monthLabel(item.month)}
          </li>
        ))}
      </ul>
      <Button size="sm" variant="outline" disabled={busy} onClick={refileAll}>
        <RefreshCw className="size-4" />
        Tout regénérer dans mes dossiers
      </Button>
    </div>
  )
}
