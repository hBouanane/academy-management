// Ce qui a bougé, et quand.
//
// Le journal existe pour un moment précis : six mois plus tard, devant une
// famille qui conteste un chiffre. « Le paiement de septembre était sur
// octobre » doit rester répondable -- et une correction qui ne laisse pas
// de trace est pire que l'erreur qu'elle corrige.
//
// Il s'ouvre donc sur TOUT, et non sur le mois affiché : la ligne qu'on
// cherche est, par définition, sur le mauvais mois.

import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Notice } from "@/components/Notice"
import { monthLabel } from "@/components/MonthNav"
import { apiGet } from "@/lib/api"
import type { JournalEntry, JournalPage } from "@/lib/api"
import { useAlert } from "@/lib/alert"
import { formatDH } from "@/lib/money"

// Le code voyage dans la base et ne change jamais ; le libellé est de
// l'affichage et se reformule sans réécrire l'histoire.
const ACTIONS: Record<string, string> = {
  payment_in: "Encaissé",
  payment_completed: "Complément encaissé",
  payment_reversed: "Paiement contre-passé",
  refund_settled: "Remboursement rendu",
  payout: "Versé",
  payout_cancelled: "Versement annulé",
  guarantee: "Professeur soldé",
  overpaid_charge: "Trop-perçu pris en charge",
  overpaid_charge_cancelled: "Prise en charge annulée",
  enrollment: "Inscrit",
  enrollment_deleted: "Désinscrit",
  adjustment: "Réduction posée",
  adjustment_changed: "Réduction modifiée",
  adjustment_deleted: "Réduction retirée",
  month_prepared: "Mois préparé",
  class_archived: "Classe archivée",
}

// Ce qui défait quelque chose se lit en retrait : la ligne compte, mais
// elle n'est pas ce qu'on parcourt.
const UNDOING = new Set([
  "payment_reversed",
  "payout_cancelled",
  "enrollment_deleted",
  "adjustment_deleted",
  "overpaid_charge_cancelled",
])

/** SQLite écrit en UTC sans le dire ; sans le « Z » le navigateur lirait
    ces heures comme locales et les décalerait d'autant. */
function when(stamp: string) {
  return new Date(`${stamp.replace(" ", "T")}Z`).toLocaleString("fr-FR", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  })
}

type Narrowing = { kind: string; id: number; label: string } | null

export function Journal({ month }: { month: string }) {
  const [entries, setEntries] = useState<JournalEntry[]>([])
  const [more, setMore] = useState<number | null>(null)
  const [onlyMonth, setOnlyMonth] = useState(false)
  const [who, setWho] = useState<Narrowing>(null)
  const [error, setError] = useAlert()
  const [busy, setBusy] = useState(false)

  const query = useCallback(
    (before: number | null) => {
      const parts = ["limit=25"]
      if (onlyMonth) parts.push(`month=${month}`)
      if (who) parts.push(`subject_kind=${who.kind}&subject_id=${who.id}`)
      if (before !== null) parts.push(`before_id=${before}`)
      return `/api/journal?${parts.join("&")}`
    },
    [month, onlyMonth, who],
  )

  // Un changement de filtre repart de la première page : garder le curseur
  // afficherait la suite d'une liste qui n'existe plus.
  useEffect(() => {
    setError(null)
    apiGet<JournalPage>(query(null))
      .then((page) => {
        setEntries(page.entries)
        setMore(page.next_before_id)
      })
      .catch((err: Error) => setError(err.message))
  }, [query, setError])

  const loadMore = () => {
    if (more === null) return
    setBusy(true)
    apiGet<JournalPage>(query(more))
      .then((page) => {
        setEntries((current) => [...current, ...page.entries])
        setMore(page.next_before_id)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-medium tracking-tight">Journal</h3>
        <p className="text-muted-foreground text-sm">
          Tout ce qui a touché à l'argent, le plus récent en premier.
        </p>
        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          onClick={() => setOnlyMonth((current) => !current)}
        >
          {onlyMonth ? "Voir tous les mois" : `Voir ${monthLabel(month)} seul`}
        </Button>
      </div>

      {/* Une liste filtrée qui ne le dit pas est une liste à qui il manque
          des lignes. La sortie est à côté de l'affirmation. */}
      {who && (
        <div className="border-border flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm">
          <span>
            Actions concernant <strong>{who.label}</strong>
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={() => setWho(null)}
          >
            Tout revoir
          </Button>
        </div>
      )}

      <Notice alert={error} />

      {entries.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          Rien pour l'instant. Les encaissements, versements et corrections
          s'inscriront ici.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Quand</TableHead>
              <TableHead>Ce qui s'est passé</TableHead>
              <TableHead>Qui</TableHead>
              <TableHead className="text-right">Montant</TableHead>
              <TableHead>Mois</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell className="text-muted-foreground whitespace-nowrap">
                  {when(entry.happened_at)}
                </TableCell>
                <TableCell
                  className={UNDOING.has(entry.action) ? "text-muted-foreground" : ""}
                >
                  {ACTIONS[entry.action] ?? entry.action}
                  {entry.detail && (
                    <span className="text-muted-foreground block text-xs">
                      {entry.detail}
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  {entry.subject_label && entry.subject_kind ? (
                    <button
                      type="button"
                      className="underline-offset-2 hover:underline"
                      title="Ne montrer que ses lignes"
                      onClick={() =>
                        setWho({
                          kind: entry.subject_kind!,
                          id: entry.subject_id!,
                          label: entry.subject_label!,
                        })
                      }
                    >
                      {entry.subject_label}
                    </button>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-right font-medium whitespace-nowrap">
                  {entry.amount_centimes === null
                    ? "—"
                    : formatDH(entry.amount_centimes)}
                </TableCell>
                <TableCell className="text-muted-foreground whitespace-nowrap capitalize">
                  {entry.month ? monthLabel(entry.month) : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {/* Pagination par curseur : le journal grandit pendant qu'on le lit,
          et un décalage ferait sauter une ligne -- celle qu'on cherche. */}
      {more !== null && (
        <Button size="sm" variant="outline" disabled={busy} onClick={loadMore}>
          {busy ? "…" : "Charger la suite"}
        </Button>
      )}
    </section>
  )
}
