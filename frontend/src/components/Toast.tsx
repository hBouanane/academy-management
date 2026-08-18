// Une confirmation qui passe : l'argent bouge, l'app le dit, ça s'efface.
//
// Sans ça, encaisser referme simplement la fenêtre — on doute d'avoir
// cliqué. Le vert dit « c'est fait », le rouge reste réservé aux vrais
// échecs (une alerte permanente en rouge finit par ne plus alerter).

import { createContext, useCallback, useContext, useState } from "react"
import { Check, TriangleAlert, X } from "lucide-react"

type Tone = "success" | "error"
type Toast = { id: number; message: string; tone: Tone }

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
      tone === "error" ? 6000 : 3500,
    )
  }, [])

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-5 bottom-5 z-100 flex flex-col items-end gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast-enter pointer-events-auto flex max-w-sm items-start gap-2 rounded-xl border px-3.5 py-2.5 text-sm shadow-lg backdrop-blur ${
              toast.tone === "success"
                ? "border-success/25 bg-success/12 text-success"
                : "border-destructive/25 bg-destructive/12 text-destructive"
            }`}
          >
            {toast.tone === "success" ? (
              <Check className="mt-0.5 size-4 shrink-0" />
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
