import { useCallback, useState } from "react"

export type Alert = {
  message: string | null
  /** How many times the alert has been raised. The text may be the same
      twice in a row; this counter never is. */
  signal: number
}

/**
 * A repeated failure must be seen again.
 *
 * With a plain `useState<string | null>`, making the same mistake sets
 * exactly the same string: React compares, finds nothing new, and does
 * not re-render. The user clicks again, fails the same way, and the
 * screen does not flinch -- he believes his action went through.
 *
 * The counter fixes that without changing any call site: `setError` keeps
 * its signature, and every raise carries a different signal.
 */
export function useAlert(): [Alert, (message: string | null) => void] {
  const [alert, setAlert] = useState<Alert>({ message: null, signal: 0 })
  const raise = useCallback((message: string | null) => {
    setAlert((previous) => ({ message, signal: previous.signal + 1 }))
  }, [])
  return [alert, raise]
}
