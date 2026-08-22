import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { ConfirmButton } from "@/components/Confirm"
import type { Payout } from "@/lib/api"
import { formatDH } from "@/lib/money"

/**
 * Every payout made to one beneficiary this month.
 *
 * These were chips in a cell: an amount and a date squeezed onto a button
 * that also cancelled it, with the receipt hidden behind a small icon.
 * Two destructive-ish actions and a date, all inside one pill -- and no
 * column to read down when there were three of them.
 *
 * As a table each payout is a line with its two actions written out. The
 * amount and the date are read, not decoded, and « Annuler » says what it
 * does instead of being the pill itself.
 */
export function PayoutHistory({
  name,
  payouts,
  canPrint,
  onPrint,
  onCancel,
  onClose,
}: {
  name: string
  payouts: Payout[]
  /** Only a teacher has a receipt to sign; the salle and the owner do not. */
  canPrint: boolean
  onPrint: (payoutId: number) => void
  onCancel: (payoutId: number) => void
  onClose: () => void
}) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Versements — {name}</DialogTitle>
        </DialogHeader>

        {payouts.length === 0 && (
          <p className="text-muted-foreground text-sm">
            Aucun versement ce mois-ci.
          </p>
        )}

        {payouts.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead className="text-right">Montant</TableHead>
                <TableHead>Note</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {payouts.map((payout) => (
                <TableRow key={payout.id}>
                  <TableCell>{payout.paid_on}</TableCell>
                  <TableCell className="text-right font-medium">
                    {formatDH(payout.amount_centimes)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {payout.note ?? "—"}
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    {canPrint && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="mr-1"
                        title="Le reçu signé de ce versement"
                        onClick={() => onPrint(payout.id)}
                      >
                        Imprimer le reçu
                      </Button>
                    )}
                    <ConfirmButton
                      size="sm"
                      variant="ghost"
                      confirmLabel="Annuler ce versement ?"
                      description="L'argent revient dans la caisse et le reste à sortir remonte d'autant. Le reçu déjà sorti est renommé « annulé » plutôt que supprimé : le professeur en a peut-être déjà un exemplaire signé."
                      onConfirm={() => onCancel(payout.id)}
                    >
                      Annuler
                    </ConfirmButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <p className="text-muted-foreground text-xs">
          Un reçu ne se refait pas : il constate ce qui a été remis ce jour-là.
          Le rouvrir montre celui qui a été signé.
        </p>
      </DialogContent>
    </Dialog>
  )
}
