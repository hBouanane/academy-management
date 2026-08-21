import { useEffect, useRef, useState } from "react"
import { Lock, ShieldCheck } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Notice } from "@/components/Notice"
import { useAlert } from "@/lib/alert"
import { apiGet, apiSend, setSessionToken } from "@/lib/api"

type Props = {
  onOpened: () => void
}

/** Three doors, never shown together: the code on an ordinary morning,
    the phrase written on paper, and the vendor rescue when the first two
    are lost. */
type Mode = "code" | "phrase" | "editeur"

const TITLES: Record<Mode, string> = {
  code: "Académie verrouillée",
  phrase: "Phrase de secours",
  editeur: "Dépannage par l'éditeur",
}

const SUBTITLES: Record<Mode, string> = {
  code: "Entrez votre code pour continuer.",
  phrase:
    "Entrez la phrase notée le jour où vous avez posé le code, puis choisissez-en un nouveau.",
  editeur:
    "Envoyez à l'éditeur le code ci-dessous. Il vous renverra un texte à coller, valable aujourd'hui seulement.",
}

/**
 * The screen that guards the academy.
 *
 * An ordinary morning sees only a field and a button. The second path,
 * the recovery phrase, appears only when asked for -- it is the emergency
 * exit of an application with no network, where nobody can reset a code
 * remotely.
 *
 * Setting the code happens elsewhere, on the Academy page: here, the door
 * is already shut.
 */
export function LockScreen({ onOpened }: Props) {
  const [code, setCode] = useState("")
  const [phrase, setPhrase] = useState("")
  const [answer, setAnswer] = useState("")
  const [mode, setMode] = useState<Mode>("code")
  const [busy, setBusy] = useState(false)
  // The challenge to dictate to the vendor -- absent from builds shipped
  // without a key.
  const [rescue, setRescue] = useState<{
    available: boolean
    challenge?: string
  } | null>(null)
  // The fresh phrase returned by a rescue: shown once, here.
  const [freshPhrase, setFreshPhrase] = useState<string | null>(null)
  const [error, setError] = useAlert()
  const field = useRef<HTMLTextAreaElement>(null)

  const switchTo = (next: Mode) => {
    setMode(next)
    setCode("")
    setPhrase("")
    setAnswer("")
  }

  const codeField = useRef<HTMLInputElement>(null)
  const phraseField = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const target =
      mode === "code" ? codeField : mode === "phrase" ? phraseField : field
    target.current?.focus()
  }, [mode])

  useEffect(() => {
    apiGet<{ available: boolean; challenge?: string }>("/api/lock/rescue")
      .then(setRescue)
      .catch(() => setRescue({ available: false }))
  }, [])

  const submit = async () => {
    setBusy(true)
    try {
      if (mode === "phrase")
        await apiSend("POST", "/api/lock/recover", {
          phrase: phrase.trim().toLowerCase(),
          code,
        })
      if (mode === "editeur") {
        const rescued = await apiSend<{ recovery_phrase: string }>(
          "POST",
          "/api/lock/rescue",
          { answer: answer.trim(), code },
        )
        // The lost phrase is replaced: he leaves with his own again,
        // otherwise he would depend on the vendor forever.
        setFreshPhrase(rescued.recovery_phrase)
        return
      }
      const opened = await apiSend<{ token: string }>("POST", "/api/lock/unlock", {
        code,
      })
      setSessionToken(opened.token)
      onOpened()
    } catch (err) {
      setError((err as Error).message)
      setCode("")
      codeField.current?.focus()
    } finally {
      setBusy(false)
    }
  }

  if (freshPhrase)
    return (
      <div className="bg-background fixed inset-0 z-50 flex items-center justify-center p-6">
        <div className="view-enter w-full max-w-sm space-y-4">
          <div className="space-y-1.5 text-center">
            <ShieldCheck className="text-muted-foreground mx-auto size-7" />
            <h1 className="text-xl font-medium tracking-tight">
              Votre nouvelle phrase de secours
            </h1>
            <p className="text-muted-foreground text-sm">
              L'ancienne ne vaut plus rien. Notez celle-ci sur papier : sans
              elle, il faudra recontacter l'éditeur.
            </p>
          </div>
          <p className="border-border bg-muted/60 rounded-lg border p-3 text-center font-mono text-lg tracking-wide select-all">
            {freshPhrase}
          </p>
          <Button
            className="w-full"
            onClick={() => {
              void navigator.clipboard.writeText(freshPhrase).catch(() => {})
              void apiSend<{ token: string }>("POST", "/api/lock/unlock", {
                code,
              }).then((opened) => {
                setSessionToken(opened.token)
                onOpened()
              })
            }}
          >
            Je l'ai notée — entrer
          </Button>
        </div>
      </div>
    )

  return (
    <div className="bg-background fixed inset-0 z-50 flex items-center justify-center p-6">
      <div className="view-enter w-full max-w-sm space-y-4">
        <div className="space-y-1.5 text-center">
          <Lock className="text-muted-foreground mx-auto size-7" />
          <h1 className="text-xl font-medium tracking-tight">{TITLES[mode]}</h1>
          <p className="text-muted-foreground text-sm">{SUBTITLES[mode]}</p>
        </div>

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!busy) void submit()
          }}
        >
          {mode === "phrase" && (
            <div className="space-y-1.5">
              <Label htmlFor="lock-phrase">Phrase de secours</Label>
              <Input
                id="lock-phrase"
                ref={phraseField}
                value={phrase}
                onChange={(event) => setPhrase(event.target.value)}
                placeholder="pomme-sentier-lampe-tortue-42"
                autoComplete="off"
              />
            </div>
          )}
          {mode === "editeur" && (
            <div className="space-y-2">
              <div className="space-y-1">
                <Label>Envoyez ce code à l'éditeur</Label>
                <p className="border-border bg-muted/60 rounded-lg border p-2.5 text-center font-mono text-base tracking-widest select-all">
                  {rescue?.challenge}
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lock-answer">Sa réponse</Label>
                {/* A signature is eighty-eight characters: it gets
                    pasted, not typed. */}
                <textarea
                  id="lock-answer"
                  ref={field}
                  value={answer}
                  onChange={(event) => setAnswer(event.target.value)}
                  placeholder="Collez ici le texte envoyé par l'éditeur"
                  rows={3}
                  spellCheck={false}
                  className="border-input bg-background focus-visible:ring-ring w-full resize-none rounded-md border px-3 py-2 font-mono text-xs break-all focus-visible:ring-1 focus-visible:outline-none"
                />
              </div>
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="lock-code">
              {mode === "code" ? "Code" : "Nouveau code"}
            </Label>
            <Input
              id="lock-code"
              ref={mode === "code" ? codeField : undefined}
              type="password"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              autoComplete="off"
            />
          </div>
          <Notice alert={error} />
          <Button type="submit" className="w-full" disabled={busy || code.length < 4}>
            {mode === "code" ? "Entrer" : "Reposer un code"}
          </Button>
        </form>

        <div className="flex flex-col items-center gap-1.5">
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground text-xs underline-offset-2 hover:underline"
            onClick={() => switchTo(mode === "code" ? "phrase" : "code")}
          >
            {mode === "code" ? "Code oublié ?" : "Revenir au code"}
          </button>
          {/* The last resort: both the code AND the phrase are lost. It
              appears only if this build carries a vendor key. */}
          {rescue?.available && mode !== "editeur" && (
            <button
              type="button"
              className="text-muted-foreground/70 hover:text-foreground text-xs underline-offset-2 hover:underline"
              onClick={() => switchTo("editeur")}
            >
              Phrase perdue aussi — contacter l'éditeur
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
