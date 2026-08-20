import { useEffect, useRef } from "react"
import { Info, TriangleAlert } from "lucide-react"

import { useToast } from "@/components/Toast"
import type { Alert } from "@/lib/alert"

type Tone = "error" | "warning" | "info"

type Props = {
  /** Texte qui suit l'état de l'écran : il apparaît et disparaît avec
      la condition qui le provoque. Reste sur place. */
  message?: string | null
  /** Alerte levée par une ACTION — celle qui doit se revoir à chaque
      échec, et qui flotte pour se faire voir. */
  alert?: Alert
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

/**
 * Deux choses différentes, et c'est la distinction qui compte.
 *
 * Un ÉCHEC répond à un geste : « code incorrect », « il reste 200 DH ».
 * Il flotte, se lit, s'efface, et revient si l'on refait la même
 * erreur — posé en bas d'un formulaire, il se retrouvait hors de
 * l'écran au moment précis où il avait quelque chose à dire.
 *
 * Un AVERTISSEMENT D'ÉTAT décrit ce que l'écran montre en ce moment :
 * « les pourcentages dépassent 100 ». Celui-là reste sur place, près du
 * champ fautif, et s'en va tout seul dès que c'est corrigé. Le faire
 * flotter était une erreur : une bulle ne peut pas se rétracter, alors
 * elle restait à l'écran alors que le problème était déjà réglé — et
 * elle s'affichait même au chargement, le temps que les champs se
 * remplissent.
 */
export function Notice({ message, alert, tone = "error", className = "" }: Props) {
  return alert ? (
    <FloatingFailure alert={alert} tone={tone} />
  ) : (
    <StandingWarning message={message} tone={tone} className={className} />
  )
}

/** L'échec d'un geste : il rejoint la pile flottante. */
function FloatingFailure({ alert, tone }: { alert: Alert; tone: Tone }) {
  const toast = useToast()
  const last = useRef<number | null>(null)

  useEffect(() => {
    if (!alert.message || alert.signal === 0) {
      last.current = null
      return
    }
    // Chaque levée compte, même identique à la précédente : refaire la
    // même erreur doit se revoir.
    if (last.current === alert.signal) return
    last.current = alert.signal
    toast(alert.message, tone)
  }, [alert.message, alert.signal, tone, toast])

  return null
}

/** L'état de l'écran : il reste tant que le problème est là. */
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
