import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import type { ComponentProps } from "react"

type Props = ComponentProps<typeof Button> & {
  confirmLabel?: string
  onConfirm: () => void
}

/** Two-step inline safeguard: first click arms ("Confirmer ?"), second fires.
    Disarms itself after 3 seconds — no accidental destructive clicks. */
export function ConfirmButton({
  children,
  confirmLabel = "Confirmer ?",
  onConfirm,
  ...props
}: Props) {
  const [armed, setArmed] = useState(false)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
    }
  }, [])

  const click = () => {
    if (!armed) {
      setArmed(true)
      timer.current = window.setTimeout(() => setArmed(false), 3000)
      return
    }
    if (timer.current) window.clearTimeout(timer.current)
    setArmed(false)
    onConfirm()
  }

  return (
    <Button
      {...props}
      variant={armed ? "destructive" : props.variant}
      onClick={click}
    >
      {armed ? confirmLabel : children}
    </Button>
  )
}
