import { useCallback, useEffect, useState } from "react"
import { Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ConfirmButton } from "@/components/Confirm"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"
import type { MessageTemplate } from "@/lib/api"

/** Ce que l'application sait remplir. Écrit en toutes lettres : personne
    ne devine une liste de repères. */
const MARKERS = [
  ["{eleve}", "le nom de l'élève"],
  ["{mois}", "le mois concerné"],
  ["{montant}", "ce qu'il reste à payer"],
  ["{classes}", "ses matières"],
  ["{academie}", "le nom de votre académie"],
]

/** Quand un message a un sens. Proposer « vous n'avez pas payé » à une
    famille qui vient de régler ferait désinstaller l'application. */
const WHEN: { value: MessageTemplate["shown_when"]; label: string }[] = [
  { value: "always", label: "Toujours" },
  { value: "unpaid", label: "S'il reste à payer" },
  { value: "paid", label: "Une fois payé" },
]

/**
 * Ses messages à lui.
 *
 * Les trois posés à l'installation ne sont pas « les messages du
 * logiciel » : ce sont déjà les siens. Il les reprend à son goût, les
 * traduit — « salam khouya {eleve}, had chhar makhallastich » — les
 * jette, en ajoute d'autres. Un logiciel qui impose sa façon de dire
 * les choses finit contourné : il recopiera à la main, et se trompera
 * de montant.
 */
export function MessageTemplates({
  onError,
}: {
  onError: (message: string) => void
}) {
  const [templates, setTemplates] = useState<MessageTemplate[]>([])
  const [label, setLabel] = useState("")
  const [body, setBody] = useState("")
  const [when, setWhen] = useState<MessageTemplate["shown_when"]>("always")
  const toast = useToast()

  const load = useCallback(
    () =>
      apiGet<MessageTemplate[]>("/api/message-templates")
        .then(setTemplates)
        .catch(() => setTemplates([])),
    [],
  )
  useEffect(() => {
    void load()
  }, [load])

  const add = () =>
    apiSend("POST", "/api/message-templates", { label, body, shown_when: when })
      .then(() => {
        setLabel("")
        setBody("")
        setWhen("always")
        toast(`Modèle « ${label} » ajouté`)
        void load()
      })
      .catch((err: Error) => onError(err.message))

  const save = (template: MessageTemplate, patch: Partial<MessageTemplate>) =>
    apiSend("PATCH", `/api/message-templates/${template.id}`, patch)
      .then(load)
      .catch((err: Error) => onError(err.message))

  return (
    <div className="surface-card space-y-4 p-6">
      <div>
        <Label>Mes messages</Label>
        <p className="text-muted-foreground text-xs">
          Trois sont là pour commencer — reprenez-les à votre goût,
          traduisez-les, jetez-les, ajoutez les vôtres. Ils apparaîtront
          sur chaque élève, avec les valeurs remplies.
        </p>
      </div>

      <p className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 text-xs">
        {MARKERS.map(([marker, what]) => (
          <span key={marker}>
            <code className="bg-muted rounded px-1 py-0.5">{marker}</code> {what}
          </span>
        ))}
      </p>

      {templates.map((template) => (
        <div
          key={template.id}
          className="border-border space-y-2 rounded-xl border p-3"
        >
          <div className="flex items-center gap-2">
            <Input
              value={template.label}
              onChange={(event) =>
                setTemplates((current) =>
                  current.map((entry) =>
                    entry.id === template.id
                      ? { ...entry, label: event.target.value }
                      : entry,
                  ),
                )
              }
              onBlur={(event) => save(template, { label: event.target.value })}
              className="h-8 w-56 text-sm font-medium"
            />
            <span className="flex-1" />
            <WhenPicker
              value={template.shown_when}
              onChange={(next) => save(template, { shown_when: next })}
            />
            <ConfirmButton
              size="sm"
              variant="ghost"
              title="Supprimer ce modèle"
              confirmLabel="Supprimer ?"
              description="Ce message ne sera plus proposé."
              onConfirm={() =>
                apiSend("DELETE", `/api/message-templates/${template.id}`)
                  .then(load)
                  .catch((err: Error) => onError(err.message))
              }
            >
              <Trash2 className="size-4" />
            </ConfirmButton>
          </div>
          <textarea
            value={template.body}
            onChange={(event) =>
              setTemplates((current) =>
                current.map((entry) =>
                  entry.id === template.id
                    ? { ...entry, body: event.target.value }
                    : entry,
                ),
              )
            }
            onBlur={(event) => save(template, { body: event.target.value })}
            rows={3}
            className="border-input bg-background focus-visible:ring-ring w-full resize-y rounded-md border px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none"
          />
        </div>
      ))}

      <div className="border-border space-y-2 rounded-xl border border-dashed p-3">
        <Input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Nom du modèle — « Rappel darija »"
          className="h-8 w-64 text-sm"
        />
        <textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder="salam khouya {eleve}, had chhar makhallastich"
          rows={3}
          className="border-input bg-background focus-visible:ring-ring w-full resize-y rounded-md border px-3 py-2 text-sm focus-visible:ring-1 focus-visible:outline-none"
        />
        <WhenPicker value={when} onChange={setWhen} />
        <Button
          size="sm"
          disabled={!label.trim() || !body.trim()}
          onClick={add}
        >
          <Plus className="size-4" />
          Ajouter ce modèle
        </Button>
      </div>
    </div>
  )
}

/** Trois pastilles valent mieux qu'une liste déroulante : on voit les
    trois choix sans cliquer. */
function WhenPicker({
  value,
  onChange,
}: {
  value: MessageTemplate["shown_when"]
  onChange: (next: MessageTemplate["shown_when"]) => void
}) {
  return (
    <span className="flex flex-wrap gap-1">
      {WHEN.map((entry) => (
        <button
          key={entry.value}
          type="button"
          onClick={() => onChange(entry.value)}
          className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
            value === entry.value
              ? "border-transparent bg-primary text-primary-foreground font-medium"
              : "border-border text-muted-foreground hover:border-foreground/40"
          }`}
        >
          {entry.label}
        </button>
      ))}
    </span>
  )
}
