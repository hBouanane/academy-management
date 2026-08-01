import { useEffect, useState } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
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
import { monthLabel, nextMonth } from "@/components/MonthNav"
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import type { ClassRow, Package } from "@/lib/api"
import { currentMonth, formatDH, previousMonth } from "@/lib/money"

type Props = {
  studentId: number
  studentName: string
  levelId: number
  month: string
  onDone: () => void
  /** Called with the new enrollment id — used to chain into the pay dialog. */
  onEnrolled?: (enrollmentId: number) => void
  /** Controlled mode: when provided, the dialog renders without a trigger
      button (used right after creating a student). */
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

const todayIso = () => {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  return `${now.getFullYear()}-${month}-${String(now.getDate()).padStart(2, "0")}`
}

// Enrolling for the running month starts today by default (the prorata rule);
// a coming month starts empty, meaning full price.
const defaultStart = (month: string) =>
  month === currentMonth() ? todayIso() : ""

export function EnrollDialog({
  studentId,
  studentName,
  levelId,
  month,
  onDone,
  onEnrolled,
  open: controlledOpen,
  onOpenChange,
}: Props) {
  const [internalOpen, setInternalOpen] = useState(false)
  const open = controlledOpen ?? internalOpen
  const setOpen = onOpenChange ?? setInternalOpen

  const [packages, setPackages] = useState<Package[]>([])
  const [classes, setClasses] = useState<ClassRow[]>([])
  const [proration, setProration] = useState<number[]>([10000, 6700, 3300])
  const [selectedMonth, setSelectedMonth] = useState(month)
  const [packageId, setPackageId] = useState<string>("")
  const [selectedClasses, setSelectedClasses] = useState<number[]>([])
  const [arrival, setArrival] = useState("")
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setSelectedMonth(month)
    setArrival(defaultStart(month))
    apiGet<Package[]>("/api/packages").then(setPackages).catch(() => {})
    apiGet<ClassRow[]>("/api/classes").then(setClasses).catch(() => {})
    apiGet<{ proration_bp: number[] }[]>("/api/academies")
      .then(([academy]) => academy && setProration(academy.proration_bp))
      .catch(() => {})
  }, [open, month])

  const reset = () => {
    setSelectedClasses([])
    setPackageId("")
    setArrival(defaultStart(month))
    setSelectedMonth(month)
    setNote(null)
    setError(null)
    setBusy(false)
  }

  const changeMonth = (target: string) => {
    setSelectedMonth(target)
    setArrival(defaultStart(target))
    setNote(null)
  }

  // A Primaire student only sees Primaire classes and Primaire packages.
  const levelClasses = classes.filter((row) => row.level_id === levelId)
  const levelPackages = packages.filter(
    (pack) => pack.level_id === null || pack.level_id === levelId,
  )
  const chosenPackage = packages.find((p) => String(p.id) === packageId)
  const capacity = chosenPackage?.subject_count ?? 0
  const full = chosenPackage !== undefined && selectedClasses.length >= capacity

  // Mirror of the backend proration formula, for the live price hint.
  const proratedHint = (() => {
    if (!chosenPackage || !arrival || arrival.slice(0, 7) !== selectedMonth)
      return null
    const day = Number(arrival.slice(8, 10))
    const daysInMonth = new Date(
      Number(selectedMonth.slice(0, 4)),
      Number(selectedMonth.slice(5, 7)),
      0,
    ).getDate()
    const index = Math.min(
      Math.floor((day - 1) / (daysInMonth / proration.length)),
      proration.length - 1,
    )
    return Math.floor(
      (chosenPackage.monthly_price_centimes * proration[index]) / 10000,
    )
  })()

  const toggleClass = (classId: number, checked: boolean) => {
    setSelectedClasses((current) =>
      checked ? [...current, classId] : current.filter((id) => id !== classId),
    )
  }

  const submit = () => {
    if (!chosenPackage) {
      setNote("Aucun forfait choisi — sélectionnez-en un d'abord.")
      return
    }
    if (selectedClasses.length !== capacity) {
      setNote(
        `Cochez ${capacity} matière(s) — il en manque ${
          capacity - selectedClasses.length
        }.`,
      )
      return
    }
    if (arrival && arrival.slice(0, 7) !== selectedMonth) {
      setNote(
        "La date de début doit être dans le mois d'inscription — changez de" +
          " mois avec les flèches ou corrigez la date.",
      )
      return
    }
    setNote(null)
    setError(null)
    setBusy(true)
    apiSend<{ id: number }>("POST", "/api/enrollments", {
      student_id: studentId,
      month: selectedMonth,
      package_id: chosenPackage.id,
      class_ids: selectedClasses,
      arrival_date: arrival || null,
    })
      .then((created) => {
        setOpen(false)
        reset()
        onDone()
        onEnrolled?.(created.id)
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
          <DialogTitle>Inscrire {studentName}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="border-border flex items-center justify-between rounded-lg border p-1">
            <Button
              variant="ghost"
              size="sm"
              title="Mois précédent"
              onClick={() => changeMonth(previousMonth(selectedMonth))}
            >
              <ChevronLeft className="size-4" />
            </Button>
            <span className="text-sm font-medium capitalize">
              {monthLabel(selectedMonth)}
              {selectedMonth > currentMonth() && (
                <span className="text-muted-foreground ml-2 text-xs font-normal">
                  mois à venir
                </span>
              )}
              {selectedMonth < currentMonth() && (
                <span className="text-muted-foreground ml-2 text-xs font-normal">
                  rattrapage — impayé immédiat
                </span>
              )}
            </span>
            <Button
              variant="ghost"
              size="sm"
              title="Mois suivant"
              onClick={() => changeMonth(nextMonth(selectedMonth))}
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
          <div className="space-y-2">
            <Label>Forfait</Label>
            <Select
              value={packageId}
              onValueChange={(value) => {
                setPackageId(value)
                setSelectedClasses([])
                setNote(null)
              }}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Choisir un forfait" />
              </SelectTrigger>
              <SelectContent>
                {levelPackages.map((pack) => (
                  <SelectItem key={pack.id} value={String(pack.id)}>
                    {pack.subject_count} matière(s) —{" "}
                    {formatDH(pack.monthly_price_centimes)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {levelPackages.length === 0 && (
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
          <div className="space-y-2">
            <Label>
              Date de début{" "}
              <span className="text-muted-foreground">(prorata)</span>
            </Label>
            <Input
              type="date"
              min={`${selectedMonth}-01`}
              max={`${selectedMonth}-31`}
              value={arrival}
              onChange={(event) => setArrival(event.target.value)}
            />
            {proratedHint !== null && chosenPackage && (
              <p className="text-muted-foreground text-xs">
                Prix au prorata :{" "}
                <span className="text-foreground line-through">
                  {formatDH(chosenPackage.monthly_price_centimes)}
                </span>{" "}
                <span className="text-foreground font-medium">
                  {formatDH(proratedHint)}
                </span>
              </p>
            )}
            <p className="text-muted-foreground text-xs">
              {selectedMonth === currentMonth()
                ? "Aujourd'hui par défaut — changez la date si l'étudiant commence plus tard."
                : "Laissez vide pour le tarif plein du mois."}
            </p>
          </div>
          <Notice message={note} />
          <Notice message={error} />
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : "Inscrire"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
