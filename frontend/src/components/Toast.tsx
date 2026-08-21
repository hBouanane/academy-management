// A confirmation that passes through: money moves, the app says so, it
// fades.
//
// Without it, taking a payment simply closes the window -- and you doubt
// you clicked. Green says « it is done »; red stays reserved for genuine
// failures (a permanent red alert ends up alerting nobody).

import { createContext, useCallback, useContext, useState } from "react"
import { Check, Info, TriangleAlert, X } from "lucide-react"

type Tone = "success" | "error" | "warning" | "info"
type Toast = {
  id: number
  message: string
  tone: Tone
  /** The catch-up: « Enregistrer ailleurs… » AFTER the fact, rather than a
      second button that would re-ask the question before every gesture. */
  action?: { label: string; run: () => void }
}

// A failure stays longer than a confirmation: there is something to read
// and often something to correct.
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

type Push = (
  message: string,
  tone?: Tone,
  action?: () => void,
  actionLabel?: string,
) => void

const ToastContext = createContext<Push>(() => {})

/** `toast("Encaissé : 300,00 DH")` — vert par défaut, rouge sur échec. */
export const useToast = () => useContext(ToastContext)

export function ToastHost({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const push = useCallback<Push>(
    (message, tone = "success", run, actionLabel = "Enregistrer ailleurs…") => {
    const id = Date.now() + Math.random()
    const action = run ? { label: actionLabel, run } : undefined
    setToasts((current) => [...current, { id, message, tone, action }])
    window.setTimeout(
      () => setToasts((current) => current.filter((entry) => entry.id !== id)),
      // A bubble that OFFERS something must stay long enough to be taken
      // up: three seconds is enough to read, not to decide.
      action ? 9000 : LIVES[tone],
    )
    },
    [],
  )

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
            <span className="min-w-0 flex-1 break-words">
              {toast.message}
              {toast.action && (
                <>
                  {" · "}
                  <button
                    type="button"
                    className="underline underline-offset-2 opacity-80 hover:opacity-100"
                    onClick={() => {
                      toast.action?.run()
                      setToasts((current) =>
                        current.filter((entry) => entry.id !== toast.id),
                      )
                    }}
                  >
                    {toast.action.label}
                  </button>
                </>
              )}
            </span>
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
