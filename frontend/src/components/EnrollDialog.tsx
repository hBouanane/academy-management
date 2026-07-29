import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { apiGet, apiSend } from "@/lib/api"
import type { ClassRow, Package } from "@/lib/api"
import { formatDH } from "@/lib/money"

type Props = {
  studentId: number
  studentName: string
  levelId: number
  month: string
  onDone: () => void
  /** Controlled mode: when provided, the dialog renders without a trigger
      button (used right after creating a student). */
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

export function EnrollDialog({
  studentId,
  studentName,
  levelId,
  month,
  onDone,
  open: controlledOpen,
  onOpenChange,
}: Props) {
  const [internalOpen, setInternalOpen] = useState(false)
  const open = controlledOpen ?? internalOpen
  const setOpen = onOpenChange ?? setInternalOpen

  const [packages, setPackages] = useState<Package[]>([])
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [packageId, setPackageId] = useState<string>("")
  const [selectedClasses, setSelectedClasses] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    apiGet<Package[]>("/api/packages").then(setPackages).catch(() => {})
    apiGet<ClassRow[]>("/api/classes").then(setClasses).catch(() => {})
  }, [open])

  const reset = () => {
    setSelectedClasses([])
    setPackageId("")
    setError(null)
    setBusy(false)
  }

  // A Primaire student only sees Primaire classes.
  const levelClasses = classes.filter((row) => row.level_id === levelId)
  const chosenPackage = packages.find((p) => String(p.id) === packageId)
  const capacity = chosenPackage?.subject_count ?? 0
  const full = chosenPackage !== undefined && selectedClasses.length >= capacity
  const ready = chosenPackage !== undefined && selectedClasses.length === capacity

  const toggleClass = (classId: number, checked: boolean) => {
    setSelectedClasses((current) =>
      checked ? [...current, classId] : current.filter((id) => id !== classId),
    )
  }

  const submit = () => {
    if (!chosenPackage) return
    setError(null)
    setBusy(true)
    apiSend("POST", "/api/enrollments", {
      student_id: studentId,
      month,
      package_id: chosenPackage.id,
      class_ids: selectedClasses,
    })
      .then(() => {
        setOpen(false)
        reset()
        onDone()
      })
      .catch((err: Error) => {
        setError(err.message)
        setBusy(false)
      })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) reset()
      }}
    >
      {controlledOpen === undefined && (
        <DialogTrigger asChild>
          <Button size="sm" variant="outline">
            Inscrire
          </Button>
        </DialogTrigger>
      )}
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            Inscrire {studentName} — {month}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Forfait</Label>
            <Select
              value={packageId}
              onValueChange={(value) => {
                setPackageId(value)
                setSelectedClasses([])
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Choisir un forfait" />
              </SelectTrigger>
              <SelectContent>
                {packages.map((pack) => (
                  <SelectItem key={pack.id} value={String(pack.id)}>
                    {pack.subject_count} matière(s) —{" "}
                    {formatDH(pack.monthly_price_centimes)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {packages.length === 0 && (
              <p className="text-muted-foreground text-sm">
                Aucun forfait — créez-en un dans la page Forfaits.
              </p>
            )}
          </div>
          <div className="space-y-2">
            <Label>
              Matières{" "}
              {chosenPackage && (
                <span className="text-muted-foreground">
                  ({selectedClasses.length}/{capacity})
                </span>
              )}
            </Label>
            <div className="border-border max-h-48 space-y-2 overflow-y-auto rounded-lg border p-3">
              {levelClasses.map((classRow) => {
                const checked = selectedClasses.includes(classRow.id)
                const disabled = !chosenPackage || (!checked && full)
                return (
                  <label
                    key={classRow.id}
                    className={`flex items-center gap-2 text-sm ${disabled && !checked ? "opacity-40" : ""}`}
                  >
                    <Checkbox
                      checked={checked}
                      disabled={disabled}
                      onCheckedChange={(state) =>
                        toggleClass(classRow.id, state === true)
                      }
                    />
                    {classRow.subject_name} — {classRow.teacher_name}
                  </label>
                )
              })}
              {levelClasses.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  Aucune classe pour ce niveau — créez-en dans la page Classes.
                </p>
              )}
            </div>
            {!chosenPackage && (
              <p className="text-muted-foreground text-xs">
                Choisissez d'abord un forfait.
              </p>
            )}
          </div>
          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={!ready || busy}>
            {busy ? "…" : "Inscrire"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
