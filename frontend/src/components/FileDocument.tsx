import { FolderDown } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useToast } from "@/components/Toast"
import { apiSend } from "@/lib/api"

type Props = {
  kind: "payslip" | "absence" | "excel"
  month: string
  refId?: number
  /** Le dossier n'est pas encore choisi : le bouton le dit au lieu de
      disparaître, sinon on ne saurait pas que la fonction existe. */
  ready: boolean
  className?: string
  children?: React.ReactNode
}

/**
 * « Ranger dans mes dossiers » : l'application écrit le document à sa
 * place — un dossier par mois, un tiroir par sorte — au lieu de laisser
 * le propriétaire choisir un emplacement à chaque fois et retrouver
 * quinze fichiers en vrac dans Téléchargements.
 *
 * Le lien « Enregistrer sous… » reste à côté : le choix ne disparaît
 * pas, il cesse seulement d'être obligatoire.
 */
export function FileDocument({
  kind,
  month,
  refId = 0,
  ready,
  className = "",
  children,
}: Props) {
  const toast = useToast()
  return (
    <Button
      size="sm"
      variant="outline"
      className={className}
      title={
        ready
          ? "Ranger dans le dossier de sauvegarde"
          : "Choisissez d'abord un dossier de sauvegarde (page Académie)"
      }
      onClick={() =>
        apiSend<{ path: string }>("POST", "/api/documents/file", {
          kind,
          month,
          ref_id: refId,
        })
          .then((filed) => toast(`Rangé dans ${filed.path}`))
          .catch((err: Error) => toast(err.message, "error"))
      }
    >
      <FolderDown className="size-4" />
      {children ?? "Ranger"}
    </Button>
  )
}
