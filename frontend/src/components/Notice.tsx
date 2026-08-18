import { useEffect, useState } from "react"
import { Info, TriangleAlert, X } from "lucide-react"

import type { Alert } from "@/lib/alert"

type Tone = "error" | "warning" | "info"

type Props = {
  /** Texte fixe, pour les avertissements qui suivent l'état de l'écran. */
  message?: string | null
  /** Alerte levée par une action — celle qui doit se revoir à chaque échec. */
  alert?: Alert
  /** 0 = reste jusqu'à ce qu'on la ferme. Par défaut, un échec reste,
      un avertissement s'efface. */
  duration?: number
  className?: string
  /** Tout en rouge finit par ne plus alerter : l'avertissement est ambre,
      l'information neutre, le rouge reste pour ce qui a vraiment échoué. */
  tone?: Tone
}

const TONES: Record<Tone, string> = {
  error: "border-destructive/40 bg-destructive/10 text-destructive",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-600",
  info: "border-border bg-muted/60 text-muted-foreground",
}

/** A note that knows how loud to be: a failure stays until it is closed,
    a warning fades on its own, and either reappears when its message
    changes — or, when it is fed an Alert, whenever the same failure
    happens again. */
export function Notice({
  message,
  alert,
  duration,
  className = "",
  tone = "error",
}: Props) {
  const text = alert ? alert.message : message
  // Un échec qui s'efface tout seul laisse croire qu'il n'a pas eu lieu :
  // il reste tant qu'on ne l'a pas fermé. Un avertissement, lui, a fait
  // son travail dès qu'il a été lu.
  const life = duration ?? (tone === "error" ? 0 : 8000)
  // Ce qui identifie CETTE apparition : le texte seul pour un
  // avertissement d'état, le numéro de la levée pour un échec — sinon
  // deux refus identiques ne feraient qu'une seule apparition.
  const token = alert ? `${alert.signal}` : `${text}`
  const [dismissed, setDismissed] = useState<string | null>(null)

  useEffect(() => {
    if (!text || life <= 0) return
    const timer = window.setTimeout(() => setDismissed(token), life)
    return () => window.clearTimeout(timer)
  }, [text, token, life])

  if (!text || dismissed === token) return null
  const Icon = tone === "info" ? Info : TriangleAlert
  return (
    <p
      // Le remontage rejoue l'animation : un deuxième refus se voit
      // bouger, même mot pour mot identique au premier.
      key={token}
      className={`notice-enter flex items-start gap-2 rounded-lg border p-2.5 text-sm ${TONES[tone]} ${className}`}
    >
      <Icon className="mt-0.5 size-4 shrink-0" />
      <span className="min-w-0 flex-1 break-words">{text}</span>
      <button
        type="button"
        aria-label="Fermer"
        onClick={() => setDismissed(token)}
        className="shrink-0 opacity-60 transition-opacity hover:opacity-100"
      >
        <X className="size-4" />
      </button>
    </p>
  )
}
