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
  month: string
  onDone: () => void
}

export function EnrollDialog({ studentId, studentName, month, onDone }: Props) {
  const [open, setOpen] = useState(false)
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

  const chosenPackage = packages.find((p) => String(p.id) === packageId)
  const ready =
    chosenPackage !== undefined &&
    selectedClasses.length === chosenPackage.subject_count

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
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          Inscrire
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            Inscrire {studentName} — {month}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Forfait</Label>
            <Select value={packageId} onValueChange={setPackageId}>
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
                Aucun forfait — créez-en un dans Paramètres.
              </p>
            )}
          </div>
          <div className="space-y-2">
            <Label>Matières ({selectedClasses.length} choisie(s))</Label>
            <div className="max-h-48 space-y-2 overflow-y-auto rounded-md border p-3">
              {classes.map((classRow) => (
                <label
                  key={classRow.id}
                  className="flex items-center gap-2 text-sm"
                >
                  <Checkbox
                    checked={selectedClasses.includes(classRow.id)}
                    onCheckedChange={(checked) =>
                      toggleClass(classRow.id, checked === true)
                    }
                  />
                  {classRow.subject_name} — {classRow.teacher_name} (
                  {classRow.level_name})
                </label>
              ))}
              {classes.length === 0 && (
                <p className="text-muted-foreground text-sm">
                  Aucune classe — créez-en dans Paramètres.
                </p>
              )}
            </div>
          </div>
          {chosenPackage && !ready && (
            <p className="text-muted-foreground text-sm">
              Choisissez exactement {chosenPackage.subject_count} matière(s)
              pour ce forfait.
            </p>
          )}
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
