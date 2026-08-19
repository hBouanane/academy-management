import { useCallback, useEffect, useRef, useState } from "react"

import { apiGet, apiSend, setSessionToken, whenLocked } from "@/lib/api"
import type { LockState } from "@/lib/api"

/**
 * Le verrou, vu de l'interface.
 *
 * Le vrai moment de risque n'est pas le démarrage : c'est le portable
 * laissé ouvert sur le bureau pendant le cours. D'où la minuterie —
 * quelques minutes sans un geste et l'écran se referme, sans rien
 * perdre de ce qui était affiché.
 *
 * Le serveur reste seul juge : s'il répond « verrouillée » à un appel,
 * l'écran remonte de lui-même, même si la minuterie n'avait pas fini.
 */
export function useLock() {
  const [state, setState] = useState<LockState | null>(null)
  const [open, setOpen] = useState(false)
  const timer = useRef<number | null>(null)

  const refresh = useCallback(
    () =>
      apiGet<LockState>("/api/lock")
        .then((lock) => {
          setState(lock)
          // Pas de code posé : rien à garder, on entre.
          if (!lock.configured) setOpen(true)
          return lock
        })
        .catch(() => setState(null)),
    [],
  )
  useEffect(() => {
    void refresh()
  }, [refresh])

  const close = useCallback(() => {
    setSessionToken(null)
    setOpen(false)
    void apiSend("POST", "/api/lock/lock").catch(() => {})
  }, [])

  // Le serveur a le dernier mot.
  useEffect(() => whenLocked(() => setOpen(false)), [])

  // Le délai vient d'être changé dans les réglages : la minuterie en
  // cours doit repartir dessus.
  useEffect(() => {
    const listen = () => void refresh()
    window.addEventListener("academy-lock-changed", listen)
    return () => window.removeEventListener("academy-lock-changed", listen)
  }, [refresh])

  // La minuterie : chaque geste la relance, son silence la fait tomber.
  useEffect(() => {
    if (!open || !state?.configured) return
    const delay = state.auto_lock_minutes * 60_000
    const restart = () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
      timer.current = window.setTimeout(close, delay)
    }
    const events = ["pointerdown", "keydown", "wheel", "focus"] as const
    for (const event of events)
      window.addEventListener(event, restart, { passive: true })
    restart()
    return () => {
      for (const event of events) window.removeEventListener(event, restart)
      if (timer.current !== null) window.clearTimeout(timer.current)
    }
  }, [open, state?.configured, state?.auto_lock_minutes, close])

  return {
    state,
    open,
    close,
    opened: () => {
      setOpen(true)
      void refresh()
    },
  }
}
