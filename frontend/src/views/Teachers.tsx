import { useCallback, useEffect, useState } from "react"
import { Pencil, UserMinus, UserPlus } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ConfirmButton } from "@/components/Confirm"
import { MonthNav } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { TeacherDialog } from "@/components/TeacherDialog"
import { TeacherProfile } from "@/components/TeacherProfile"
import { apiGet, apiSend } from "@/lib/api"
import type { Teacher } from "@/lib/api"
import { formatDH } from "@/lib/money"

type Row = Teacher & {
  created_at: string | null
  subjects: string | null
  earned_centimes: number
  is_active: number
}

type Props = { month: string; setMonth: (month: string) => void }

export function Teachers({ month, setMonth }: Props) {
  const [rows, setRows] = useState<Row[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // "new" opens creation; a row opens edition (identity + capability tree).
  const [editing, setEditing] = useState<Row | "new" | null>(null)
  const [profileId, setProfileId] = useState<number | null>(null)

  const reload = useCallback(() => {
    apiGet<Row[]>(`/api/teachers?include_inactive=${showArchived}&month=${month}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message))
  }, [showArchived, month])
  useEffect(reload, [reload])

  const setActive = (row: Row, active: boolean) => {
    setBusy(true)
    apiSend("PATCH", `/api/teachers/${row.id}`, { is_active: active })
      .then(reload)
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Professeurs</h2>
          <p className="text-muted-foreground text-sm">
            Tout part d'ici : créez le professeur, cochez son arbre — les
            classes s'ouvrent ensuite en un clic
          </p>
        </div>
        <div className="flex items-center gap-2">
          <MonthNav month={month} setMonth={setMonth} />
          <Button onClick={() => setEditing("new")}>
            <UserPlus className="size-4" /> Nouveau professeur
          </Button>
        </div>
      </header>

      <Notice message={error} />

      <div className="surface-card p-5">
        <label className="text-muted-foreground mb-4 flex items-center gap-2 text-sm">
          <Checkbox
            checked={showArchived}
            onCheckedChange={(checked) => setShowArchived(checked === true)}
          />
          Afficher les professeurs archivés
        </label>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Nom</TableHead>
              <TableHead>Rôle</TableHead>
              <TableHead>Téléphone</TableHead>
              <TableHead>Depuis</TableHead>
              <TableHead>Matières</TableHead>
              <TableHead className="text-right">Gagné ({month})</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, index) => (
              <TableRow
                key={row.id}
                className="stagger-row cursor-pointer"
                style={{ animationDelay: `${index * 40}ms` }}
                title="Ouvrir le profil"
                onClick={(event) => {
                  if ((event.target as HTMLElement).closest("button, a")) return
                  setProfileId(row.id)
                }}
              >
                <TableCell className="font-medium">{row.name}</TableCell>
                <TableCell>
                  {row.is_owner ? (
                    <Badge variant="outline">Propriétaire</Badge>
                  ) : (
                    <span className="text-muted-foreground text-xs">—</span>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {row.phone ?? "—"}
                </TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {row.created_at?.slice(0, 10) ?? "—"}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {row.subjects ?? "—"}
                </TableCell>
                <TableCell className="text-right">
                  <span
                    className={
                      Number(row.earned_centimes) > 0
                        ? "text-success font-medium"
                        : ""
                    }
                  >
                    {formatDH(Number(row.earned_centimes ?? 0))}
                  </span>
                </TableCell>
                <TableCell className="space-x-1 text-right whitespace-nowrap">
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Modifier — identité et arbre des compétences"
                    onClick={() => setEditing(row)}
                  >
                    <Pencil className="size-4" />
                  </Button>
                  <ConfirmButton
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    confirmLabel={row.is_active ? "Archiver ?" : "Restaurer ?"}
                    description="Réversible — il continue de recevoir ses anciens mois quand ils sont encaissés."
                    title={row.is_active ? "Archiver (réversible)" : "Restaurer"}
                    onConfirm={() => setActive(row, !row.is_active)}
                  >
                    {row.is_active ? (
                      <UserMinus className="size-4" />
                    ) : (
                      <UserPlus className="size-4" />
                    )}
                  </ConfirmButton>
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-muted-foreground text-center">
                  Aucun professeur — créez le premier, tout part de là.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <TeacherDialog
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        initial={editing === "new" ? null : editing}
        onSaved={() => {
          setEditing(null)
          reload()
        }}
      />

      <TeacherProfile
        teacherId={profileId}
        month={month}
        onClose={() => setProfileId(null)}
        onChanged={reload}
      />
    </div>
  )
}
