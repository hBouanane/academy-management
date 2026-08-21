import { useEffect, useRef } from "react"
import { Info, TriangleAlert } from "lucide-react"

import { useToast } from "@/components/Toast"
import type { Alert } from "@/lib/alert"

type Tone = "error" | "warning" | "info"

type Props = {
  /** Text that follows the screen's state: it appears and disappears with
      the condition that caused it. Stays in place. */
  message?: string | null
  /** An alert raised by an ACTION -- the kind that must be seen again on
      every failure, and floats to make itself seen. */
  alert?: Alert
  className?: string
  /** All-red stops alerting anyone: warnings are amber, information is
      neutral, and red is kept for what genuinely failed. */
  tone?: Tone
}

const TONES: Record<Tone, string> = {
  error: "border-destructive/40 bg-destructive/10 text-destructive",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-600",
  info: "border-border bg-muted/60 text-muted-foreground",
}

/**
 * Two different things, and the distinction is what matters.
 *
 * A FAILURE answers a gesture: « code incorrect », « il reste 200 DH ».
 * It floats, is read, fades, and comes back if the same mistake is made
 * again -- placed at the bottom of a form, it ended up off-screen at the
 * exact moment it had something to say.
 *
 * A STATE WARNING describes what the screen is showing right now: « les
 * pourcentages dépassent 100 ». That one stays put, next to the offending
 * field, and leaves by itself once corrected. Making it float was a
 * mistake: a bubble cannot retract, so it stayed on screen while the
 * problem was already fixed -- and it even appeared during loading, while
 * the fields were still filling in.
 */
export function Notice({ message, alert, tone = "error", className = "" }: Props) {
  return alert ? (
    <FloatingFailure alert={alert} tone={tone} />
  ) : (
    <StandingWarning message={message} tone={tone} className={className} />
  )
}

/** A gesture's failure: it joins the floating stack. */
function FloatingFailure({ alert, tone }: { alert: Alert; tone: Tone }) {
  const toast = useToast()
  const last = useRef<number | null>(null)

  useEffect(() => {
    if (!alert.message || alert.signal === 0) {
      last.current = null
      return
    }
    // Every raise counts, even one identical to the last: making the same
    // mistake again must be seen again.
    if (last.current === alert.signal) return
    last.current = alert.signal
    toast(alert.message, tone)
  }, [alert.message, alert.signal, tone, toast])

  return null
}

/** The screen's state: it stays as long as the problem does. */
function StandingWarning({
  message,
  tone,
  className,
}: {
  message?: string | null
  tone: Tone
  className: string
}) {
  if (!message) return null
  const Icon = tone === "info" ? Info : TriangleAlert
  return (
    <p
      className={`flex items-start gap-2 rounded-lg border p-2.5 text-sm ${TONES[tone]} ${className}`}
    >
      <Icon className="mt-0.5 size-4 shrink-0" />
      <span className="min-w-0 flex-1 break-words">{message}</span>
    </p>
  )
}
