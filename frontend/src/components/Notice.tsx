import { useEffect, useState } from "react"
import { X } from "lucide-react"

type Props = {
  message: string | null
  duration?: number
  className?: string
}

/** Red note with a life span: fades away on a timer, closable with the X,
    and reappears whenever its message changes. */
export function Notice({ message, duration = 8000, className = "" }: Props) {
  const [dismissed, setDismissed] = useState<string | null>(null)

  useEffect(() => {
    if (!message || duration <= 0) return
    const timer = window.setTimeout(() => setDismissed(message), duration)
    return () => window.clearTimeout(timer)
  }, [message, duration])

  if (!message || dismissed === message) return null
  return (
    <p
      className={`border-destructive/40 bg-destructive/10 text-destructive flex items-start gap-2 rounded-lg border p-2.5 text-sm ${className}`}
    >
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
