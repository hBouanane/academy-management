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
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import type { Level, Package } from "@/lib/api"
import { dhToCentimes, formatDH } from "@/lib/money"

// The three natural price points for a bloc niveau — labels editable,
// prices HIS to type (they are price variants, never reductions).
const DEFAULT_VARIANTS = ["1ère–4ème année", "5ème–6ème année", "Cas particulier"]

function VariantScaffold({
  levelId,
  busy,
  onDone,
  onError,
}: {
  levelId: number
  busy: boolean
  onDone: () => void
  onError: (message: string) => void
}) {
  const [drafts, setDrafts] = useState(
    DEFAULT_VARIANTS.map((label) => ({ label, price: "" })),
  )
  const [saving, setSaving] = useState(false)

  const createAll = async () => {
    const filled = drafts.filter((draft) => draft.price.trim())
    if (filled.length === 0) return
    setSaving(true)
    try {
      for (const draft of filled) {
        await apiSend("POST", "/api/packages", {
          level_id: levelId,
          subject_count: 1,
          monthly_price_centimes: dhToCentimes(draft.price),
          label: draft.label.trim() || null,
        })
      }
      onDone()
    } catch (err) {
      onError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border-border mt-3 space-y-2 rounded-xl border border-dashed p-3">
      <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        Démarrage rapide — trois variantes, entrez vos prix
      </p>
      {drafts.map((draft, index) => (
        <div key={index} className="flex flex-wrap items-center gap-2">
          <Input
            value={draft.label}
            onChange={(event) =>
              setDrafts((current) =>
                current.map((entry, i) =>
                  i === index ? { ...entry, label: event.target.value } : entry,
                ),
              )
            }
            className="w-48"
          />
          <Input
            type="number"
            min="0"
            placeholder="Prix (DH)"
            value={draft.price}
            onChange={(event) =>
              setDrafts((current) =>
                current.map((entry, i) =>
                  i === index ? { ...entry, price: event.target.value } : entry,
                ),
              )
            }
            className="w-28"
          />
        </div>
      ))}
      <Button
        size="sm"
        onClick={createAll}
        disabled={saving || busy || drafts.every((draft) => !draft.price.trim())}
      >
        {saving ? "…" : "Créer les variantes remplies"}
      </Button>
    </div>
  )
}

export function Packages() {
  const [packages, setPackages] = useState<Package[]>([])
  const [levels, setLevels] = useState<Level[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [levelId, setLevelId] = useState("")
  const [count, setCount] = useState("1")
  const [price, setPrice] = useState("")
  const [label, setLabel] = useState("")
  const [editing, setEditing] = useState<Package | null>(null)
  const [editCount, setEditCount] = useState("")
  const [editPrice, setEditPrice] = useState("")
  const [editLabel, setEditLabel] = useState("")
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

  // Bloc niveaux (Primaire, Formation): one group, all matières together —
  // forfaits are pure PRICE VARIANTS there (1 matière, optional label).
  const isBloc = (level: Level | null | undefined) =>
    level !== null && level !== undefined && level.teaching_annees === 0
  const chosenLevel = levels.find((level) => String(level.id) === levelId)

  const create = () =>
    run(async () => {
      await apiSend("POST", "/api/packages", {
        level_id: Number(levelId),
        subject_count: isBloc(chosenLevel) ? 1 : Number(count),
        monthly_price_centimes: dhToCentimes(price),
        label: label.trim() || null,
      })
      setPrice("")
      setLabel("")
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

      <Notice message={error} />

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
          {!isBloc(chosenLevel) && (
            <Input
              type="number"
              min="1"
              max="8"
              value={count}
              onChange={(event) => setCount(event.target.value)}
              className="w-24"
              placeholder="Matières"
            />
          )}
          <Input
            type="number"
            min="0"
            placeholder="Prix (DH)"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            className="w-32"
          />
          <Input
            placeholder="Étiquette (optionnelle)"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            className="w-48"
          />
          <Button onClick={create} disabled={!levelId || !price || busy}>
            Ajouter
          </Button>
        </div>
        {isBloc(chosenLevel) && (
          <p className="text-muted-foreground text-xs">
            {chosenLevel?.name} : un seul groupe, toutes matières — le forfait
            est une simple variante de prix (ce n'est pas une réduction).
          </p>
        )}
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
          <h3 className="font-medium">
            {group.level?.name ?? "Tous niveaux (anciens forfaits)"}
          </h3>
          {isBloc(group.level) && (
            <p className="text-muted-foreground mb-2 text-sm">
              Variantes de prix — il choisit la bonne pour chaque étudiant
            </p>
          )}
          <div className="table-wrap mt-3">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    {isBloc(group.level) ? "Étiquette" : "Matières"}
                  </TableHead>
                  <TableHead>Prix mensuel</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {group.rows.map((pack) => (
                  <TableRow key={pack.id}>
                    <TableCell>
                      {isBloc(group.level)
                        ? (pack.label ?? "—")
                        : `${pack.subject_count} matière(s)` +
                          (pack.label ? ` · ${pack.label}` : "")}
                    </TableCell>
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
                          setEditLabel(pack.label ?? "")
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
                      {isBloc(group.level)
                        ? "Aucune variante de prix"
                        : "Aucun forfait pour ce niveau"}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
          {/* The 1ère–4ème / 5ème–6ème split is a Primaire concept — other
              bloc niveaux (Formation, …) get the plain "＋ variante" row
              above instead of a scaffold that wouldn't fit them. */}
          {group.level?.name === "Primaire" &&
            group.rows.length === 0 && (
              <VariantScaffold
                levelId={group.level.id}
                busy={busy}
                onDone={reload}
                onError={setError}
              />
            )}
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
            {!isBloc(levels.find((level) => level.id === editing?.level_id)) && (
              <div className="space-y-2">
                <Label>Nombre de matières</Label>
                <Input
                  type="number"
                  min="1"
                  value={editCount}
                  onChange={(event) => setEditCount(event.target.value)}
                />
              </div>
            )}
            <div className="space-y-2">
              <Label>Prix mensuel (DH)</Label>
              <Input
                type="number"
                min="0"
                value={editPrice}
                onChange={(event) => setEditPrice(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>
                Étiquette <span className="text-muted-foreground">(optionnelle)</span>
              </Label>
              <Input
                value={editLabel}
                onChange={(event) => setEditLabel(event.target.value)}
                placeholder="1ère–4ème année, Cas particulier…"
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
                    label: editLabel.trim() || null,
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
