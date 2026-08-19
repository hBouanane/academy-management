import { useEffect, useState } from "react"
import { FileText } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"
import type { Folders } from "@/lib/api"

type Props = {
  kind: "payslip" | "absence" | "excel"
  month: string
  refId?: number
  /** L'adresse du téléchargement classique, pour « Enregistrer sous… ». */
  downloadHref: string
  size?: "sm" | "default"
  variant?: "default" | "outline" | "ghost"
  className?: string
  title?: string
  children?: React.ReactNode
}

/**
 * Un seul bouton par document.
 *
 * Deux boutons côte à côte reposaient à chaque fois la question qu'un
 * dossier choisi une fois pour toutes était censé supprimer. Alors le
 * bouton décide : un dossier est désigné, il y range et dit où ; aucun
 * dossier, il ouvre l'enregistrement ordinaire de Windows.
 *
 * L'autre chemin ne disparaît pas — il passe APRÈS. Le mot de
 * confirmation porte « Enregistrer ailleurs… », pour la fois sur vingt
 * où l'on voulait un autre endroit. On agit d'abord, on corrige
 * ensuite, au lieu de choisir vingt fois pour un cas.
 */
export function FileDocument({
  kind,
  month,
  refId = 0,
  downloadHref,
  size = "sm",
  variant = "outline",
  className = "",
  title,
  children,
}: Props) {
  const [folder, setFolder] = useState<string | null>(null)
  const toast = useToast()

  useEffect(() => {
    apiGet<Folders>("/api/settings/folders")
      .then((settings) => setFolder(settings.documents.path))
      .catch(() => setFolder(null))
  }, [])

  const saveAs = () => {
    const link = document.createElement("a")
    link.href = downloadHref
    link.download = ""
    link.click()
  }

  const run = () => {
    if (folder === null) {
      saveAs()
      toast(
        "Choisissez un dossier dans la page Académie pour ne plus avoir à ranger vous-même",
        "info",
      )
      return
    }
    apiSend<{ path: string }>("POST", "/api/documents/file", {
      kind,
      month,
      ref_id: refId,
    })
      .then((filed) => toast(placeOf(filed.path), "success", saveAs))
      .catch((err: Error) => toast(err.message, "error"))
  }

  return (
    <Button
      size={size}
      variant={variant}
      className={className}
      title={title ?? "Enregistrer ce document"}
      onClick={run}
    >
      <FileText className="size-4" />
      {children}
    </Button>
  )
}

/** « Septembre › fiches-de-paie » se lit ; le chemin entier, non. */
function placeOf(path: string) {
  const parts = path.replace(/\\/g, "/").split("/")
  const file = parts.at(-1)
  const place = parts.slice(-3, -1).join(" › ").replace(/^\d{4}-\d{2} /, "")
  return `${file} rangé dans ${place}`
}
