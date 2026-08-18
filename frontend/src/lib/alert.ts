import { useCallback, useState } from "react"

export type Alert = {
  message: string | null
  /** Combien de fois l'alerte a été levée. Le texte peut être le même
      deux fois de suite ; ce compteur, jamais. */
  signal: number
}

/**
 * Un échec répété doit se revoir.
 *
 * Avec un simple `useState<string | null>`, refaire la même erreur pose
 * exactement la même chaîne : React compare, ne trouve rien de nouveau,
 * et ne rerend pas. L'utilisateur reclique, échoue pareil, et l'écran
 * ne bronche pas — il croit que son geste est passé.
 *
 * Le compteur règle ça sans rien changer aux appels : `setError` garde
 * sa signature, et chaque levée porte un signal différent.
 */
export function useAlert(): [Alert, (message: string | null) => void] {
  const [alert, setAlert] = useState<Alert>({ message: null, signal: 0 })
  const raise = useCallback((message: string | null) => {
    setAlert((previous) => ({ message, signal: previous.signal + 1 }))
  }, [])
  return [alert, raise]
}
