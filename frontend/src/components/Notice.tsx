import { useEffect, useRef } from "react"

import { useToast } from "@/components/Toast"
import type { Alert } from "@/lib/alert"

type Tone = "error" | "warning" | "info"

type Props = {
  /** Texte fixe, pour les avertissements qui suivent l'état de l'écran. */
  message?: string | null
  /** Alerte levée par une action — celle qui doit se revoir à chaque échec. */
  alert?: Alert
  className?: string
  /** Tout en rouge finit par ne plus alerter : l'avertissement est ambre,
      l'information neutre, le rouge reste pour ce qui a vraiment échoué. */
  tone?: Tone
}

/**
 * Une alerte qui flotte, se lit, et s'en va.
 *
 * Elle n'occupe plus de place dans la page : posée en bas d'un
 * formulaire, elle se retrouvait hors de l'écran au moment précis où
 * elle avait quelque chose à dire — on cliquait, rien ne semblait se
 * passer. Elle rejoint donc la pile flottante, au même endroit que les
 * confirmations, et s'efface toute seule.
 *
 * Ce composant n'affiche rien lui-même : il pousse dans la pile. Les
 * appels ne changent pas — `<Notice alert={error} />` reste écrit là où
 * l'erreur naît, ce qui garde le code lisible.
 */
export function Notice({ message, alert, tone = "error" }: Props) {
  const toast = useToast()
  const text = alert ? alert.message : message
  // En mode « alerte », chaque levée compte, même identique à la
  // précédente : c'est tout l'intérêt: refaire la même erreur doit se
  // revoir. En mode « message », on ne pousse qu'à l'apparition —
  // sinon un texte qui se recalcule à chaque frappe inonderait la pile.
  const beat = alert ? alert.signal : text ? 1 : 0
  const last = useRef<number | null>(null)

  useEffect(() => {
    if (!text || beat === 0) {
      last.current = null
      return
    }
    if (last.current === beat) return
    last.current = beat
    toast(text, tone)
  }, [text, beat, tone, toast])

  return null
}
