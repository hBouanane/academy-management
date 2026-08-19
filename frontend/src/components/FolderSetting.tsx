import { FolderOpen, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { useToast } from "@/components/Toast"
import { apiSend } from "@/lib/api"

type Props = {
  kind: "documents" | "database"
  label: string
  explanation: string
  path: string | null
  /** Ce que le dossier contiendra, dit par le serveur — l'interface ne
      devine pas les noms de sous-dossiers. */
  example?: string | null
  /** Quand aucun dossier n'est choisi : dire ce qui se passe alors. */
  fallback?: string
  onChanged: () => void
  onError: (message: string) => void
}

/**
 * Désigner un dossier sur le disque.
 *
 * Personne ne connaît par cœur l'adresse de sa clé USB : on ouvre le
 * sélecteur de Windows, comme n'importe quel logiciel. Une fois choisi,
 * le chemin s'affiche — il n'y a plus rien à taper ni à valider.
 */
export function FolderSetting({
  kind,
  label,
  explanation,
  path,
  example,
  fallback,
  onChanged,
  onError,
}: Props) {
  const toast = useToast()

  const call = (method: "POST" | "DELETE", suffix: string, said: string) =>
    apiSend<{ path: string | null; cancelled?: boolean }>(
      method,
      `/api/settings/folders/${kind}${suffix}`,
    )
      .then((result) => {
        if (result.cancelled) return
        toast(said.replace("{path}", result.path ?? ""))
        onChanged()
      })
      .catch((err: Error) => onError(err.message))

  return (
    <div className="space-y-2">
      <div>
        <Label>{label}</Label>
        <p className="text-muted-foreground text-xs">{explanation}</p>
      </div>
      {path ? (
        <p className="border-border bg-muted/50 flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 font-mono text-xs break-all">
          {example ?? path}
        </p>
      ) : (
        fallback && <p className="text-muted-foreground text-xs">{fallback}</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={path ? "outline" : "default"}
          onClick={() => call("POST", "/browse", "Dossier choisi : {path}")}
        >
          <FolderOpen className="size-4" />
          {path ? "Changer de dossier" : "Choisir un dossier…"}
        </Button>
        {path && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => call("DELETE", "", "Dossier abandonné")}
          >
            <X className="size-4" />
            Ne plus utiliser
          </Button>
        )}
      </div>
    </div>
  )
}
