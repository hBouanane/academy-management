import { useEffect, useRef, useState } from "react"
import { Lock } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Notice } from "@/components/Notice"
import { useAlert } from "@/lib/alert"
import { apiSend, setSessionToken } from "@/lib/api"

type Props = {
  onOpened: () => void
}

/**
 * L'écran qui garde l'académie.
 *
 * Un matin ordinaire n'y voit qu'un champ et un bouton. Le second
 * chemin, la phrase de secours, ne se montre que si on le demande —
 * c'est la sortie de secours d'une application sans réseau, où
 * personne ne peut réinitialiser un code à distance.
 *
 * Poser le code se fait ailleurs, dans la page Académie : ici, la
 * porte est déjà fermée.
 */
export function LockScreen({ onOpened }: Props) {
  const [code, setCode] = useState("")
  const [phrase, setPhrase] = useState("")
  const [recovering, setRecovering] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useAlert()
  const field = useRef<HTMLInputElement>(null)

  useEffect(() => field.current?.focus(), [recovering])

  const submit = async () => {
    setBusy(true)
    try {
      if (recovering)
        await apiSend("POST", "/api/lock/recover", {
          phrase: phrase.trim().toLowerCase(),
          code,
        })
      const opened = await apiSend<{ token: string }>("POST", "/api/lock/unlock", {
        code,
      })
      setSessionToken(opened.token)
      onOpened()
    } catch (err) {
      setError((err as Error).message)
      setCode("")
      field.current?.focus()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-background fixed inset-0 z-50 flex items-center justify-center p-6">
      <div className="view-enter w-full max-w-sm space-y-4">
        <div className="space-y-1.5 text-center">
          <Lock className="text-muted-foreground mx-auto size-7" />
          <h1 className="text-xl font-medium tracking-tight">
            {recovering ? "Phrase de secours" : "Académie verrouillée"}
          </h1>
          <p className="text-muted-foreground text-sm">
            {recovering
              ? "Entrez la phrase notée le jour où vous avez posé le code, puis choisissez-en un nouveau."
              : "Entrez votre code pour continuer."}
          </p>
        </div>

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!busy) void submit()
          }}
        >
          {recovering && (
            <div className="space-y-1.5">
              <Label htmlFor="lock-phrase">Phrase de secours</Label>
              <Input
                id="lock-phrase"
                ref={field}
                value={phrase}
                onChange={(event) => setPhrase(event.target.value)}
                placeholder="pomme-sentier-lampe-tortue-42"
                autoComplete="off"
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="lock-code">
              {recovering ? "Nouveau code" : "Code"}
            </Label>
            <Input
              id="lock-code"
              ref={recovering ? undefined : field}
              type="password"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              autoComplete="off"
            />
          </div>
          <Notice alert={error} />
          <Button type="submit" className="w-full" disabled={busy || code.length < 4}>
            {recovering ? "Reposer un code" : "Entrer"}
          </Button>
        </form>

        <button
          type="button"
          className="text-muted-foreground hover:text-foreground w-full text-center text-xs underline-offset-2 hover:underline"
          onClick={() => {
            setRecovering(!recovering)
            setCode("")
            setPhrase("")
          }}
        >
          {recovering ? "Revenir au code" : "Code oublié ?"}
        </button>
      </div>
    </div>
  )
}
