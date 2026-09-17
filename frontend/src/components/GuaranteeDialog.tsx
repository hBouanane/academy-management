// Paying the professors even when the student has not paid.
//
// The student has not paid, but they did their work: the academie puts up
// the money, and the salle does not touch it (nothing came in, so it takes
// nothing). Nothing enters the till: the student still owes his month.
//
// PROFESSORS, plural. Three subjects usually means three of them, and all
// three have always been settled -- but this dialog showed one total and
// said « le professeur » in five places, so the owner read that he was
// settling one man. The money was right; the screen was lying about it.
//
// The breakdown is fetched, never computed here: it comes back from the
// same split the ledger will post, so what is shown cannot disagree with
// what is recorded.
//
// The suggested amount follows the days taught -- but the owner decides.
// He knows the arrangement; we do not.

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import { useAlert } from "@/lib/alert"
import { centimesToDh, dhToCentimes, formatDH } from "@/lib/money"

type Presence = "full" | "until" | "never"

type Share = { teacher_id: number; name: string | null; amount_centimes: number }

type Proposal = {
  suggested_centimes: number
  max_centimes: number
  teachers: Share[]
}

/** Un seul professeur ou plusieurs : la phrase doit tenir dans les deux
    cas, et « le(s) professeur(s) » n'est pas une phrase. */
function word(count: number, singular: string, plural: string) {
  return count > 1 ? plural : singular
}

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
  const [shares, setShares] = useState<Share[]>([])
  const [note, setNote] = useAlert()
  const [busy, setBusy] = useState(false)

  // The suggestion follows the days: it changes when attendance does.
  useEffect(() => {
    const query =
      presence === "until" ? `?present_until=${until}` : presence === "never" ? "" : ""
    if (presence === "never") {
      setProposal((current) =>
        current ? { ...current, suggested_centimes: 0 } : current,
      )
      setShares([])
      setAmount("0")
      return
    }
    apiGet<Proposal>(`/api/enrollments/${enrollmentId}/guarantee${query}`)
      .then((loaded) => {
        setProposal(loaded)
        setShares(loaded.teachers)
        setAmount(centimesToDh(loaded.suggested_centimes))
      })
      .catch((err: Error) => setNote(err.message))
  }, [enrollmentId, presence, until, setNote])

  const centimes = dhToCentimes(amount)

  // La repartition affichee doit etre celle qui sera posee. Elle est donc
  // demandee au serveur pour le montant choisi, plutot que refaite ici --
  // un partage au plus grand reste reecrit en TypeScript finirait par
  // deriver de celui du registre, et l ecran annoncerait alors une chose
  // pendant que le registre en enregistrerait une autre.
  useEffect(() => {
    if (presence === "never" || centimes === null || centimes < 0) return
    const timer = setTimeout(() => {
      const query = presence === "until" ? `&present_until=${until}` : ""
      apiGet<Proposal>(
        `/api/enrollments/${enrollmentId}/guarantee?amount_centimes=${centimes}${query}`,
      )
        .then((loaded) => setShares(loaded.teachers))
        .catch(() => undefined)
    }, 250)
    return () => clearTimeout(timer)
  }, [enrollmentId, presence, until, centimes])

  const count = proposal?.teachers.length ?? 0
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
          <DialogTitle>
            Payer {word(count, "le professeur", "les professeurs")} quand même —{" "}
            {studentName}
          </DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          L'élève n'a pas payé, mais{" "}
          {word(count, "le professeur a fait son", "les professeurs ont fait leur")}{" "}
          travail. C'est l'académie qui met l'argent, et la salle ne prend rien.
          L'élève doit toujours son mois : ceci ne change rien pour lui.
        </p>
        <div className="space-y-2">
          <Label>L'élève est venu jusqu'à quand ?</Label>
          {choice(
            "full",
            "Tout le mois",
            `${word(count, "Le professeur touche sa part entière", "Chaque professeur touche sa part entière")}.`,
          )}
          {choice(
            "until",
            "Jusqu'au…",
            `${word(count, "Le professeur touche", "Chaque professeur touche")} les jours faits.`,
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
            "Il n'est jamais venu",
            "Personne n'est payé : aucun cours n'a été donné.",
          )}
        </div>

        {/* The amount stays editable: it is his money, and he alone
            knows the arrangement made with the teacher. */}
        <div className="space-y-1.5">
          <Label htmlFor="guarantee-amount">
            Combien {word(count, "lui", "leur")} donner
          </Label>
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
            Vous pouvez donner moins, ou plus. S'il paie plus tard,{" "}
            {word(
              count,
              "le professeur ne touchera que ce qui lui manque",
              "les professeurs ne toucheront que ce qui leur manque",
            )}{" "}
            encore.
          </p>
        </div>

        {/* Qui reçoit quoi. Sans cette table, trois professeurs soldés
            ressemblaient à un seul -- un total ne dit pas combien de mains
            se tendent. */}
        {shares.length > 0 && (
          <div className="space-y-1.5">
            <Label>Qui reçoit quoi</Label>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Professeur</TableHead>
                  <TableHead className="text-right">Part</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shares.map((share) => (
                  <TableRow key={share.teacher_id}>
                    <TableCell>{share.name ?? "Professeur"}</TableCell>
                    <TableCell className="text-right font-medium">
                      {formatDH(share.amount_centimes)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

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
                ? `Donner ${formatDH(centimes)} à ${word(count, "ce professeur", `ces ${count} professeurs`)}`
                : "Ne rien donner"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
