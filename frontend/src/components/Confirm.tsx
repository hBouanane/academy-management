import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { ComponentProps } from "react"

type Props = ComponentProps<typeof Button> & {
  confirmLabel?: string
  description?: string
  onConfirm: () => void
}

/** Destructive-action safeguard: the trigger opens a small confirmation
    window — nothing fires until « Confirmer » is clicked inside it. */
export function ConfirmButton({
  children,
  confirmLabel = "Confirmer ?",
  description = "Cette action est immédiate.",
  onConfirm,
  ...props
}: Props) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button {...props} onClick={() => setOpen(true)}>
        {children}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-sm" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>{confirmLabel}</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm">{description}</p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              Annuler
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                setOpen(false)
                onConfirm()
              }}
            >
              Confirmer
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
