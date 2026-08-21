import { useEffect, useState } from "react"
import { MessageCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Notice } from "@/components/Notice"
import { useAlert } from "@/lib/alert"
import { apiGet, apiSend } from "@/lib/api"
import type { StudentMessages } from "@/lib/api"

type Props = {
  studentId: number
  studentName: string
  month: string
  onClose: () => void
}

/**
 * Telling the family, without sending anything behind his back.
 *
 * The application writes the message -- it knows the month, the classes
 * and the exact amount -- then opens WhatsApp on it. The owner rereads it
 * and presses send. Software that writes to families on its own is
 * software people distrust, and a wrong amount sent unread cannot be
 * taken back.
 *
 * The number is chosen: the student has his own, the father has his --
 * and one does not chase a schoolboy for an impayé.
 */
export function WhatsAppDialog({ studentId, studentName, month, onClose }: Props) {
  const [offer, setOffer] = useState<StudentMessages | null>(null)
  const [kind, setKind] = useState<string | null>(null)
  const [phone, setPhone] = useState<string | null>(null)
  const [error, setError] = useAlert()

  useEffect(() => {
    apiGet<StudentMessages>(`/api/students/${studentId}/messages?month=${month}`)
      .then((loaded) => {
        setOffer(loaded)
        // The likeliest first: chase an impayé, otherwise confirm. He can
        // always change it.
        setKind(
          loaded.messages.find((entry) => entry.kind === "unpaid")?.kind ??
            loaded.messages[0]?.kind ??
            null,
        )
        setPhone(loaded.phones.find((entry) => entry.whatsapp)?.whatsapp ?? null)
      })
      .catch((err: Error) => setError(err.message))
  }, [studentId, month, setError])

  const chosen = offer?.messages.find((entry) => entry.kind === kind)

  const open = () => {
    if (!phone || !chosen) return
    apiSend<{ url: string }>("POST", "/api/whatsapp", {
      phone,
      text: chosen.text,
    })
      .then(onClose)
      .catch((err: Error) => setError(err.message))
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Prévenir la famille — {studentName}</DialogTitle>
          <DialogDescription>
            WhatsApp s'ouvre avec le message déjà écrit. Vous le relisez, et
            c'est vous qui l'envoyez.
          </DialogDescription>
        </DialogHeader>
        <Notice alert={error} />

        {offer && offer.messages.length === 0 && (
          <p className="text-muted-foreground text-sm">
            Rien à annoncer pour ce mois — l'élève n'y est pas inscrit.
          </p>
        )}

        {offer && offer.messages.length > 0 && (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>À quel numéro</Label>
              {offer.phones.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  Aucun numéro sur sa fiche — ajoutez-en un pour pouvoir
                  écrire.
                </p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {offer.phones.map((entry) => (
                    <button
                      key={entry.number}
                      type="button"
                      disabled={!entry.whatsapp}
                      onClick={() => setPhone(entry.whatsapp)}
                      className={`rounded-full border px-3 py-1 text-sm transition-colors disabled:opacity-40 ${
                        phone === entry.whatsapp
                          ? "border-transparent bg-primary text-primary-foreground font-medium"
                          : "border-border hover:border-foreground/40"
                      }`}
                    >
                      {entry.tag} · {entry.number}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-1.5">
              <Label>Quel message</Label>
              <div className="flex flex-wrap gap-1.5">
                {offer.messages.map((entry) => (
                  <button
                    key={entry.kind}
                    type="button"
                    onClick={() => setKind(entry.kind)}
                    className={`rounded-full border px-3 py-1 text-sm transition-colors ${
                      kind === entry.kind
                        ? "border-transparent bg-primary text-primary-foreground font-medium"
                        : "border-border hover:border-foreground/40"
                    }`}
                  >
                    {entry.label}
                  </button>
                ))}
              </div>
            </div>

            {/* He must see the text BEFORE, not discover it inside
                WhatsApp -- that is where a wrong amount gets caught. */}
            {chosen && (
              <div className="space-y-1.5">
                <Label>Ce qui partira</Label>
                <p className="border-border bg-muted/50 rounded-lg border p-3 text-sm whitespace-pre-wrap">
                  {chosen.text}
                </p>
              </div>
            )}

            <Button className="w-full" disabled={!phone || !chosen} onClick={open}>
              <MessageCircle className="size-4" />
              Ouvrir WhatsApp
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
