import { useCallback, useEffect, useState } from "react"
import { FileText, Pencil, UserMinus, UserPlus } from "lucide-react"
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
import { ArchiveTeacherDialog } from "@/components/ArchiveTeacherDialog"
import { ConfirmButton } from "@/components/Confirm"
import { MonthNav, monthLabel } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { TeacherDialog } from "@/components/TeacherDialog"
import { TeacherProfile } from "@/components/TeacherProfile"
import { apiGet, apiSend } from "@/lib/api"
import type { ClassRow, Teacher } from "@/lib/api"
import { currentMonth, formatDH } from "@/lib/money"
import { useAlert } from "@/lib/alert"

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
  const [error, setError] = useAlert()
  const [busy, setBusy] = useState(false)
  // "new" opens creation; a row opens edition (identity + capability tree).
  const [editing, setEditing] = useState<Row | "new" | null>(null)
  const [profileId, setProfileId] = useState<number | null>(null)
  // Archiving someone who still teaches opens the guided departure instead.
  const [departing, setDeparting] = useState<Row | null>(null)

  const reload = useCallback(() => {
    setError(null)
    apiGet<Row[]>(`/api/teachers?include_inactive=${showArchived}&month=${month}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message))
  }, [showArchived, month, setError])
  useEffect(reload, [reload])

  const restore = (row: Row) => {
    setBusy(true)
    apiSend("PATCH", `/api/teachers/${row.id}`, { is_active: true })
      .then(reload)
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  const startArchive = (row: Row) => {
    setBusy(true)
    apiGet<ClassRow[]>(`/api/classes?month=${currentMonth()}`)
      .then((classes) => {
        const teaches = classes.some(
          (entry) => entry.is_active === 1 && entry.teacher_id === row.id,
        )
        if (teaches) {
          // The guided flow: each class gets a fate, then he is archived.
          setDeparting(row)
        } else {
          return apiSend("PATCH", `/api/teachers/${row.id}`, {
            is_active: false,
          }).then(reload)
        }
      })
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

      <Notice alert={error} />

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
                  // Ignore clicks bubbling out of portaled dialogs and hits
                  // on action buttons — only a true row click opens.
                  const target = event.target as HTMLElement
                  if (!event.currentTarget.contains(target)) return
                  if (target.closest("button, a")) return
                  setProfileId(row.id)
                }}
              >
                <TableCell className="font-medium">{row.name}</TableCell>
                <TableCell>
                  {row.is_owner ? (
                    <Badge variant="outline">Propriétaire + professeur</Badge>
                  ) : (
                    <Badge variant="outline">Professeur</Badge>
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
                    asChild
                    title={`Fiche de paie de ${monthLabel(month)} — à imprimer et signer`}
                  >
                    <a
                      href={`/api/teachers/${row.id}/invoice.docx?month=${month}`}
                      download
                    >
                      <FileText className="size-4" />
                    </a>
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    title="Modifier — identité et arbre des compétences"
                    onClick={() => setEditing(row)}
                  >
                    <Pencil className="size-4" />
                  </Button>
                  {row.is_active ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      title="Archiver — s'il enseigne encore, chaque classe reçoit d'abord un sort"
                      onClick={() => startArchive(row)}
                    >
                      <UserMinus className="size-4" />
                    </Button>
                  ) : (
                    <ConfirmButton
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      confirmLabel="Restaurer ?"
                      description="Il redevient actif — ses anciennes classes ne lui sont pas réattribuées automatiquement."
                      title="Restaurer"
                      onConfirm={() => restore(row)}
                    >
                      <UserPlus className="size-4" />
                    </ConfirmButton>
                  )}
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

      {departing && (
        <ArchiveTeacherDialog
          teacher={departing}
          teachers={rows.filter((row) => row.is_active === 1)}
          onClose={() => setDeparting(null)}
          onDone={() => {
            setDeparting(null)
            reload()
          }}
        />
      )}
    </div>
  )
}
