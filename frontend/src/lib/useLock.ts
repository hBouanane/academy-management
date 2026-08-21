import { useCallback, useEffect, useRef, useState } from "react"

import { apiGet, apiSend, setSessionToken, whenLocked } from "@/lib/api"
import type { LockState } from "@/lib/api"

/**
 * The lock, seen from the interface.
 *
 * The real moment of risk is not startup: it is the laptop left open on
 * the desk during a lesson. Hence the timer -- a few minutes without a
 * gesture and the screen closes, losing nothing of what was displayed.
 *
 * The server remains the sole judge: if it answers « verrouillée » to a
 * call, the screen comes back by itself, even if the timer had not
 * finished.
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
          // No code set: nothing to guard, we go in.
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

  // The delay has just been changed in the settings: the running timer
  // must restart on it.
  useEffect(() => {
    const listen = () => void refresh()
    window.addEventListener("academy-lock-changed", listen)
    return () => window.removeEventListener("academy-lock-changed", listen)
  }, [refresh])

  // The timer: every gesture restarts it, its silence brings it down.
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
