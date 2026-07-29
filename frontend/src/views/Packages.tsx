import { useCallback, useEffect, useState } from "react"
import { Archive, ArchiveRestore, Pencil } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { ConfirmButton } from "@/components/Confirm"
import { apiGet, apiSend } from "@/lib/api"
import type { Level, Package } from "@/lib/api"
import { dhToCentimes, formatDH } from "@/lib/money"

export function Packages() {
  const [packages, setPackages] = useState<Package[]>([])
  const [levels, setLevels] = useState<Level[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [levelId, setLevelId] = useState("")
  const [count, setCount] = useState("1")
  const [price, setPrice] = useState("")
  const [editing, setEditing] = useState<Package | null>(null)
  const [editCount, setEditCount] = useState("")
  const [editPrice, setEditPrice] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    apiGet<Package[]>(`/api/packages?include_inactive=${showArchived}`)
      .then(setPackages)
      .catch((err: Error) => setError(err.message))
  }, [showArchived])

  useEffect(() => {
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
  }, [])
  useEffect(reload, [reload])

  const run = (action: () => Promise<unknown>) => {
    setError(null)
    setBusy(true)
    action()
      .then(() => {
        reload()
        setEditing(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  const create = () =>
    run(async () => {
      await apiSend("POST", "/api/packages", {
        level_id: Number(levelId),
        subject_count: Number(count),
        monthly_price_centimes: dhToCentimes(price),
      })
      setPrice("")
    })

  const groups: { level: Level | null; rows: Package[] }[] = [
    ...levels.map((level) => ({
      level: level as Level | null,
      rows: packages.filter((pack) => pack.level_id === level.id),
    })),
    { level: null, rows: packages.filter((pack) => pack.level_id === null) },
  ].filter((group) => group.level !== null || group.rows.length > 0)

  return (
    <div className="view-enter space-y-6">
      <header>
        <h2 className="text-2xl font-medium tracking-tight">Forfaits</h2>
        <p className="text-muted-foreground text-sm">
          Un tableau par niveau — un forfait ne peut pas dépasser les matières
          enseignées à son niveau
        </p>
      </header>

      {error && (
        <p className="border-destructive/40 bg-destructive/10 text-destructive rounded-xl border p-3 text-sm">
          {error}
        </p>
      )}

      <div className="surface-card space-y-3 p-5">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
          Nouveau forfait
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <Select value={levelId} onValueChange={setLevelId}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Niveau" />
            </SelectTrigger>
            <SelectContent>
              {levels.map((level) => (
                <SelectItem key={level.id} value={String(level.id)}>
                  {level.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="number"
            min="1"
            max="8"
            value={count}
            onChange={(event) => setCount(event.target.value)}
            className="w-24"
            placeholder="Matières"
          />
          <Input
            type="number"
            min="0"
            placeholder="Prix (DH)"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            className="w-32"
          />
          <Button onClick={create} disabled={!levelId || !price || busy}>
            Ajouter
          </Button>
        </div>
        <label className="text-muted-foreground flex items-center gap-2 text-sm">
          <Checkbox
            checked={showArchived}
            onCheckedChange={(checked) => setShowArchived(checked === true)}
          />
          Afficher les forfaits archivés
        </label>
      </div>

      {groups.map((group, groupIndex) => (
        <div
          key={group.level?.id ?? "legacy"}
          className="surface-card stagger-row p-5"
          style={{ animationDelay: `${groupIndex * 60}ms` }}
        >
          <h3 className="mb-3 font-medium">
            {group.level?.name ?? "Tous niveaux (anciens forfaits)"}
          </h3>
          <div className="table-wrap">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Matières</TableHead>
                  <TableHead>Prix mensuel</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {group.rows.map((pack) => (
                  <TableRow key={pack.id}>
                    <TableCell>{pack.subject_count} matière(s)</TableCell>
                    <TableCell className="font-medium">
                      {formatDH(pack.monthly_price_centimes)}
                    </TableCell>
                    <TableCell>
                      {(pack as unknown as { is_active: number }).is_active ? (
                        <Badge className="bg-success/15 text-success border-success/20 border">
                          Actif
                        </Badge>
                      ) : (
                        <Badge variant="outline">Archivé</Badge>
                      )}
                    </TableCell>
                    <TableCell className="space-x-1 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        title="Modifier"
                        onClick={() => {
                          setEditing(pack)
                          setEditCount(String(pack.subject_count))
                          setEditPrice(
                            String(pack.monthly_price_centimes / 100),
                          )
                        }}
                      >
                        <Pencil className="size-4" />
                      </Button>
                      <ConfirmButton
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        confirmLabel={
                          (pack as unknown as { is_active: number }).is_active
                            ? "Archiver ce forfait ?"
                            : "Restaurer ce forfait ?"
                        }
                        description="Réversible — l'historique financier reste intact."
                        onConfirm={() =>
                          run(() =>
                            apiSend("PATCH", `/api/packages/${pack.id}`, {
                              is_active: !(
                                pack as unknown as { is_active: number }
                              ).is_active,
                            }),
                          )
                        }
                      >
                        {(pack as unknown as { is_active: number }).is_active ? (
                          <Archive className="size-4" />
                        ) : (
                          <ArchiveRestore className="size-4" />
                        )}
                      </ConfirmButton>
                    </TableCell>
                  </TableRow>
                ))}
                {group.rows.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={4}
                      className="text-muted-foreground text-center"
                    >
                      Aucun forfait pour ce niveau
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      ))}

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Modifier le forfait — {editing?.level_name ?? "Tous niveaux"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Nombre de matières</Label>
              <Input
                type="number"
                min="1"
                value={editCount}
                onChange={(event) => setEditCount(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Prix mensuel (DH)</Label>
              <Input
                type="number"
                min="0"
                value={editPrice}
                onChange={(event) => setEditPrice(event.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              disabled={busy}
              onClick={() =>
                run(() =>
                  apiSend("PATCH", `/api/packages/${editing!.id}`, {
                    subject_count: Number(editCount),
                    monthly_price_centimes: dhToCentimes(editPrice),
                  }),
                )
              }
            >
              Enregistrer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
