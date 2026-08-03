// « Solder l'impayé » — côté professeur seulement.
//
// L'étudiant n'a pas payé, mais le professeur a enseigné : il est payé pour
// les jours faits, l'académie avance l'argent, et la salle encaisse le coup
// avec elle (rien d'encaissé ⇒ rien pour la salle). Aucun argent n'entre :
// le mois reste un impayé et l'étudiant doit toujours sa dette.

import { useState } from "react"
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
import { Notice } from "@/components/Notice"
import { apiSend } from "@/lib/api"

type Presence = "full" | "until" | "never"

export function GuaranteeDialog({
  enrollmentId,
  studentName,
  month,
  onClose,
  onDone,
}: {
  enrollmentId: number
  studentName: string
  month: string
  onClose: () => void
  onDone: () => void
}) {
  const [presence, setPresence] = useState<Presence>("full")
  const [until, setUntil] = useState(`${month}-15`)
  const [stop, setStop] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = () => {
    setNote(null)
    setBusy(true)
    apiSend("POST", `/api/enrollments/${enrollmentId}/guarantee`, {
      present_until: presence === "until" ? until : null,
      never_came: presence === "never",
      stop,
    })
      .then(onDone)
      .catch((err: Error) => {
        setNote(err.message)
        setBusy(false)
      })
  }

  const choice = (value: Presence, label: string, hint: string) => (
    <label
      key={value}
      className={`flex cursor-pointer items-start gap-2 rounded-xl border p-3 text-sm ${
        presence === value ? "border-primary" : "border-border"
      }`}
    >
      <input
        type="radio"
        className="mt-1"
        checked={presence === value}
        onChange={() => setPresence(value)}
      />
      <span className="min-w-0">
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground block text-xs">{hint}</span>
      </span>
    </label>
  )

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Solder l'impayé — {studentName}</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          Le professeur est payé pour les jours enseignés : l'académie avance
          la somme et la salle ne touche rien (elle encaisse le coup avec
          elle). L'étudiant reste redevable — ceci ne solde que le professeur.
        </p>
        <div className="space-y-2">
          <Label>Jusqu'à quand l'étudiant était-il présent ?</Label>
          {choice(
            "full",
            "Présent tout le mois",
            "Le professeur reçoit sa part entière pour cet étudiant.",
          )}
          {choice(
            "until",
            "Présent jusqu'au…",
            "Le professeur reçoit la part correspondant à ces jours.",
          )}
          {presence === "until" && (
            <Input
              type="date"
              min={`${month}-01`}
              max={`${month}-31`}
              value={until}
              onChange={(event) => setUntil(event.target.value)}
            />
          )}
          {choice(
            "never",
            "Jamais venu",
            "Personne n'est payé — aucun cours n'a été donné.",
          )}
          <label className="text-muted-foreground flex items-center gap-2 pt-1 text-sm">
            <Checkbox
              checked={stop}
              onCheckedChange={(state) => setStop(state === true)}
            />
            Il a arrêté — ne pas le réinscrire le mois prochain
          </label>
        </div>
        <Notice message={note} />
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : "Payer le professeur"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
