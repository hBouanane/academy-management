import { useCallback, useEffect, useState } from "react"
import type { ReactNode } from "react"
import { Archive, ArchiveRestore, Pencil } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ConfirmButton } from "@/components/Confirm"
import { Notice } from "@/components/Notice"
import { Pagination, usePagination } from "@/components/Pagination"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { apiGet, apiSend } from "@/lib/api"
import { useAlert } from "@/lib/alert"

export type FieldSpec = {
  key: string
  label: string
  type?: "text" | "number" | "select"
  options?: [string, string][]
  placeholder?: string
  optional?: boolean
  /** Shown in the edit dialog only, never in the create form. */
  editOnly?: boolean
}

type Row = Record<string, unknown> & { id: number; is_active: number }

type Props = {
  title: string
  description: string
  endpoint: string
  columns: { key: string; label: string; render?: (row: Row) => ReactNode }[]
  fields: FieldSpec[]
  toBody?: (values: Record<string, string>) => Record<string, unknown>
  fromRow?: (row: Row) => Record<string, string>
  refreshKey?: number
  onChanged?: () => void
  /** Extra query-string parameters, e.g. "&month=2026-09". */
  query?: string
  /** Rendered on the right of the header — e.g. a month navigator. */
  headerExtra?: ReactNode
  /** Extra per-row action buttons, rendered before the pencil. */
  extraActions?: (row: Row) => ReactNode
  /** Clicking anywhere on a row (except buttons) triggers this. */
  onRowClick?: (row: Row) => void
}

const identityBody = (values: Record<string, string>) => values

export function EntityManager({
  title,
  description,
  endpoint,
  columns,
  fields,
  toBody = identityBody,
  fromRow,
  refreshKey = 0,
  onChanged,
  query = "",
  headerExtra,
  extraActions,
  onRowClick,
}: Props) {
  const [rows, setRows] = useState<Row[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [createValues, setCreateValues] = useState<Record<string, string>>({})
  const [editing, setEditing] = useState<Row | null>(null)
  const [editValues, setEditValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useAlert()

  const reload = useCallback(() => {
    apiGet<Row[]>(`${endpoint}?include_inactive=${showArchived}${query}`)
      .then(setRows)
      .catch((err: Error) => setError(err.message))
  }, [endpoint, showArchived, query, setError])

  useEffect(reload, [reload, refreshKey])

  const run = (action: () => Promise<unknown>) => {
    setError(null)
    setBusy(true)
    action()
      .then(() => {
        reload()
        onChanged?.()
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  const createReady = fields.every(
    (field) =>
      field.editOnly || field.optional || (createValues[field.key] ?? "") !== "",
  )

  const create = () =>
    run(async () => {
      await apiSend("POST", endpoint, toBody(createValues))
      setCreateValues({})
    })

  const saveEdit = () =>
    run(async () => {
      if (!editing) return
      await apiSend("PATCH", `${endpoint}/${editing.id}`, toBody(editValues))
      setEditing(null)
    })

  const setActive = (row: Row, active: boolean) =>
    run(() => apiSend("PATCH", `${endpoint}/${row.id}`, { is_active: active }))

  const openEdit = (row: Row) => {
    setEditing(row)
    setEditValues(
      fromRow?.(row) ??
        Object.fromEntries(
          fields.map((field) => [field.key, String(row[field.key] ?? "")]),
        ),
    )
  }

  const paging = usePagination(rows)

  return (
    <div className="view-enter space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
          <p className="text-muted-foreground text-sm">{description}</p>
        </div>
        {headerExtra}
      </header>

      <Notice alert={error} />

      <div className="surface-card space-y-3 p-5">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Ajouter
        </p>
        <div className="flex flex-wrap items-end gap-3">
          {fields
            .filter((field) => !field.editOnly)
            .map((field) => (
            <FieldInput
              key={field.key}
              field={field}
              value={createValues[field.key] ?? ""}
              onChange={(value) =>
                setCreateValues((current) => ({ ...current, [field.key]: value }))
              }
            />
          ))}
          <Button onClick={create} disabled={!createReady || busy}>
            Ajouter
          </Button>
        </div>
      </div>

      <div className="surface-card p-5">
        <label className="text-muted-foreground mb-4 flex items-center gap-2 text-sm">
          <Checkbox
            checked={showArchived}
            onCheckedChange={(checked) => setShowArchived(checked === true)}
          />
          Afficher les éléments archivés
        </label>
        <div className="table-wrap">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((column) => (
                <TableHead key={column.key}>{column.label}</TableHead>
              ))}
              <TableHead>Statut</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paging.visible.map((row, index) => (
              <TableRow
                key={row.id}
                className={`group stagger-row ${onRowClick ? "cursor-pointer" : ""}`}
                style={{ animationDelay: `${index * 40}ms` }}
                onClick={(event) => {
                  if (!onRowClick) return
                  if ((event.target as HTMLElement).closest("button, a")) return
                  onRowClick(row)
                }}
              >
                {columns.map((column) => (
                  <TableCell key={column.key}>
                    {column.render ? column.render(row) : String(row[column.key] ?? "—")}
                  </TableCell>
                ))}
                <TableCell>
                  {row.is_active ? (
                    <Badge className="bg-success/15 text-success border-success/20 border">
                      Actif
                    </Badge>
                  ) : (
                    <Badge variant="outline">Archivé</Badge>
                  )}
                </TableCell>
                <TableCell className="space-x-1 text-right whitespace-nowrap">
                  {extraActions?.(row)}
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => openEdit(row)}
                    title="Modifier"
                  >
                    <Pencil className="size-4" />
                  </Button>
                  <ConfirmButton
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    onConfirm={() => setActive(row, !row.is_active)}
                    confirmLabel={row.is_active ? "Archiver ?" : "Restaurer ?"}
                    description="Réversible — l'élément quitte les listes, l'historique financier reste intact."
                    title={row.is_active ? "Archiver (réversible)" : "Restaurer"}
                  >
                    {row.is_active ? (
                      <Archive className="size-4" />
                    ) : (
                      <ArchiveRestore className="size-4" />
                    )}
                  </ConfirmButton>
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={columns.length + 2}
                  className="text-muted-foreground text-center"
                >
                  Rien pour l'instant
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        <Pagination
          {...paging}
          shown={paging.visible.length}
          noun="lignes"
        />
        </div>
        <p className="text-muted-foreground mt-3 text-xs">
          Rien n'est jamais supprimé définitivement — archiver retire l'élément
          des listes, l'historique financier reste intact.
        </p>
      </div>

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Modifier</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {fields.map((field) => (
              <div key={field.key} className="space-y-2">
                <Label>{field.label}</Label>
                <FieldInput
                  field={{ ...field, label: "" }}
                  value={editValues[field.key] ?? ""}
                  onChange={(value) =>
                    setEditValues((current) => ({ ...current, [field.key]: value }))
                  }
                  bare
                />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button onClick={saveEdit} disabled={busy}>
              Enregistrer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function FieldInput({
  field,
  value,
  onChange,
  bare = false,
}: {
  field: FieldSpec
  value: string
  onChange: (value: string) => void
  bare?: boolean
}) {
  const input =
    field.type === "select" ? (
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-44">
          <SelectValue placeholder={field.label || field.placeholder} />
        </SelectTrigger>
        <SelectContent>
          {(field.options ?? []).map(([optionValue, label]) => (
            <SelectItem key={optionValue} value={optionValue}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    ) : (
      <Input
        type={field.type ?? "text"}
        placeholder={field.placeholder ?? field.label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-44"
      />
    )
  if (bare) return input
  return input
}
