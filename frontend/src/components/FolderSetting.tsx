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
  /** What the folder will contain, told by the server -- the interface
      does not guess subfolder names. */
  example?: string | null
  /** When no folder is chosen: say what happens then. */
  fallback?: string
  onChanged: () => void
  onError: (message: string) => void
}

/**
 * Naming a folder on disk.
 *
 * Nobody knows their USB stick's address by heart: we open the Windows
 * picker, like any other software. Once chosen, the path is displayed --
 * there is nothing left to type or confirm.
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
