import { useEffect, useState } from "react"
import { Info, TriangleAlert, X } from "lucide-react"

type Tone = "error" | "warning" | "info"

type Props = {
  message: string | null
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

/** Red note with a life span: fades away on a timer, closable with the X,
    and reappears whenever its message changes. */
export function Notice({
  message,
  duration = 8000,
  className = "",
  tone = "error",
}: Props) {
  const [dismissed, setDismissed] = useState<string | null>(null)

  useEffect(() => {
    if (!message || duration <= 0) return
    const timer = window.setTimeout(() => setDismissed(message), duration)
    return () => window.clearTimeout(timer)
  }, [message, duration])

  if (!message || dismissed === message) return null
  const Icon = tone === "info" ? Info : TriangleAlert
  return (
    <p
      className={`flex items-start gap-2 rounded-lg border p-2.5 text-sm ${TONES[tone]} ${className}`}
    >
      <Icon className="mt-0.5 size-4 shrink-0" />
      <span className="min-w-0 flex-1 break-words">{message}</span>
      <button
        type="button"
        aria-label="Fermer"
        onClick={() => setDismissed(message)}
        className="shrink-0 opacity-60 transition-opacity hover:opacity-100"
      >
        <X className="size-4" />
      </button>
    </p>
  )
}
