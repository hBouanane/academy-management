// Payer le professeur même si l'élève n'a pas payé.
//
// L'élève n'a pas payé, mais le professeur a fait son travail : c'est
// l'académie qui met l'argent, et la salle n'y touche pas (rien n'est
// entré, elle ne prend rien). Rien n'entre en caisse : l'élève doit
// toujours son mois.
//
// Le montant proposé suit les jours faits — mais c'est le propriétaire
// qui décide. Il connaît l'arrangement, pas nous.

import { useEffect, useState } from "react"
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
import { apiGet, apiSend } from "@/lib/api"
import { useAlert } from "@/lib/alert"
import { centimesToDh, dhToCentimes, formatDH } from "@/lib/money"

type Presence = "full" | "until" | "never"

type Proposal = { suggested_centimes: number; max_centimes: number }

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
  const [amount, setAmount] = useState("")
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [note, setNote] = useAlert()
  const [busy, setBusy] = useState(false)

  // La proposition suit les jours : elle change quand la présence change.
  useEffect(() => {
    const query =
      presence === "until" ? `?present_until=${until}` : presence === "never" ? "" : ""
    if (presence === "never") {
      setProposal((current) =>
        current ? { ...current, suggested_centimes: 0 } : current,
      )
      setAmount("0")
      return
    }
    apiGet<Proposal>(`/api/enrollments/${enrollmentId}/guarantee${query}`)
      .then((loaded) => {
        setProposal(loaded)
        setAmount(centimesToDh(loaded.suggested_centimes))
      })
      .catch((err: Error) => setNote(err.message))
  }, [enrollmentId, presence, until, setNote])

  const centimes = dhToCentimes(amount)
  const valid =
    centimes !== null &&
    centimes >= 0 &&
    (proposal === null || centimes <= proposal.max_centimes)

  const submit = () => {
    setNote(null)
    setBusy(true)
    apiSend("POST", `/api/enrollments/${enrollmentId}/guarantee`, {
      present_until: presence === "until" ? until : null,
      never_came: presence === "never",
      stop,
      amount_centimes: centimes,
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
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Payer le professeur quand même — {studentName}</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          L'élève n'a pas payé, mais le professeur a fait son travail. C'est
          l'académie qui met l'argent, et la salle ne prend rien. L'élève doit
          toujours son mois : ceci ne change rien pour lui.
        </p>
        <div className="space-y-2">
          <Label>L'élève est venu jusqu'à quand ?</Label>
          {choice("full", "Tout le mois", "Le professeur touche sa part entière.")}
          {choice("until", "Jusqu'au…", "Le professeur touche les jours faits.")}
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
            "Il n'est jamais venu",
            "Personne n'est payé : aucun cours n'a été donné.",
          )}
        </div>

        {/* Le montant reste modifiable : c'est son argent, et lui seul
            connaît l'arrangement passé avec le professeur. */}
        <div className="space-y-1.5">
          <Label htmlFor="guarantee-amount">Combien lui donner</Label>
          <div className="flex items-center gap-2">
            <Input
              id="guarantee-amount"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              className="w-32"
              inputMode="decimal"
            />
            <span className="text-muted-foreground text-sm">DH</span>
            {proposal && (
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground text-xs underline-offset-2 hover:underline"
                onClick={() => setAmount(centimesToDh(proposal.suggested_centimes))}
              >
                proposé : {formatDH(proposal.suggested_centimes)}
              </button>
            )}
          </div>
          <p className="text-muted-foreground text-xs">
            Vous pouvez donner moins, ou plus. S'il paie plus tard, le
            professeur ne touchera que ce qui lui manque encore.
          </p>
        </div>

        <label className="text-muted-foreground flex items-center gap-2 text-sm">
          <Checkbox
            checked={stop}
            onCheckedChange={(state) => setStop(state === true)}
          />
          Il a arrêté — ne pas le réinscrire le mois prochain
        </label>

        <Notice alert={note} />
        <DialogFooter>
          <Button onClick={submit} disabled={busy || !valid}>
            {busy
              ? "…"
              : centimes
                ? `Donner ${formatDH(centimes)} au professeur`
                : "Ne rien donner"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
