// Une confirmation qui passe : l'argent bouge, l'app le dit, ça s'efface.
//
// Sans ça, encaisser referme simplement la fenêtre — on doute d'avoir
// cliqué. Le vert dit « c'est fait », le rouge reste réservé aux vrais
// échecs (une alerte permanente en rouge finit par ne plus alerter).

import { createContext, useCallback, useContext, useState } from "react"
import { Check, Info, TriangleAlert, X } from "lucide-react"

type Tone = "success" | "error" | "warning" | "info"
type Toast = { id: number; message: string; tone: Tone }

// Un echec reste plus longtemps qu'une confirmation : il y a quelque
// chose a lire et souvent a corriger.
const LIVES: Record<Tone, number> = {
  success: 3500,
  error: 7000,
  warning: 7000,
  info: 5000,
}

const TONES: Record<Tone, string> = {
  success: "border-success/25 bg-success/12 text-success",
  error: "border-destructive/25 bg-destructive/12 text-destructive",
  warning: "border-amber-500/30 bg-amber-500/12 text-amber-600",
  info: "border-border bg-muted/80 text-foreground",
}

const ToastContext = createContext<(message: string, tone?: Tone) => void>(
  () => {},
)

/** `toast("Encaissé : 300,00 DH")` — vert par défaut, rouge sur échec. */
export const useToast = () => useContext(ToastContext)

export function ToastHost({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const push = useCallback((message: string, tone: Tone = "success") => {
    const id = Date.now() + Math.random()
    setToasts((current) => [...current, { id, message, tone }])
    window.setTimeout(
      () => setToasts((current) => current.filter((entry) => entry.id !== id)),
      LIVES[tone],
    )
  }, [])

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-5 bottom-5 z-100 flex flex-col items-end gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`${
              toast.tone === "error" ? "notice-enter" : "toast-enter"
            } pointer-events-auto flex max-w-sm items-start gap-2 rounded-xl border px-3.5 py-2.5 text-sm shadow-lg backdrop-blur ${TONES[toast.tone]}`}
          >
            {toast.tone === "success" ? (
              <Check className="mt-0.5 size-4 shrink-0" />
            ) : toast.tone === "info" ? (
              <Info className="mt-0.5 size-4 shrink-0" />
            ) : (
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            )}
            <span className="min-w-0 flex-1 break-words">{toast.message}</span>
            <button
              type="button"
              aria-label="Fermer"
              className="shrink-0 opacity-60 transition-opacity hover:opacity-100"
              onClick={() =>
                setToasts((current) =>
                  current.filter((entry) => entry.id !== toast.id),
                )
              }
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
