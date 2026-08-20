import { useEffect, useRef, useState } from "react"
import { ImageUp, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { useToast } from "@/components/Toast"
import { apiGet, apiSend } from "@/lib/api"

/** Deux mégaoctets : de quoi faire une belle enseigne, pas une photo de
    vacances. Le logo entre dans CHAQUE sauvegarde. */
const POIDS_MAX = 2 * 1024 * 1024

/**
 * Son logo, celui qui s'affiche en haut de la barre.
 *
 * Rangé dans la base et non dans un dossier : il part ainsi avec les
 * sauvegardes. Un fichier posé sur le bureau puis effacé laisserait un
 * carré vide au prochain démarrage.
 */
export function LogoSetting({ onError }: { onError: (m: string) => void }) {
  const [logo, setLogo] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const toast = useToast()

  useEffect(() => {
    apiGet<{ logo: string | null }>("/api/settings/logo")
      .then((answer) => setLogo(answer.logo))
      .catch(() => setLogo(null))
  }, [])

  const save = async (value: string | null) => {
    await apiSend("PUT", "/api/settings/logo", { logo: value })
      .then(() => {
        setLogo(value)
        // La barre de gauche écoute : elle se met à jour sans qu'on
        // relance l'application.
        window.dispatchEvent(new Event("academy-changed"))
        toast(value ? "Logo enregistré" : "Logo retiré")
      })
      .catch((err: Error) => onError(err.message))
  }

  const chosen = (file: File | undefined) => {
    if (!file) return
    if (!file.type.startsWith("image/")) {
      onError("Ce fichier n'est pas une image. Choisissez un PNG ou un JPEG.")
      return
    }
    if (file.size > POIDS_MAX) {
      onError(
        "Cette image est trop lourde : elle entrerait dans chacune de vos sauvegardes. Prenez-en une plus légère.",
      )
      return
    }
    const reader = new FileReader()
    reader.onload = () => save(String(reader.result))
    reader.onerror = () => onError("Ce fichier n'a pas pu être lu.")
    reader.readAsDataURL(file)
  }

  return (
    <div className="space-y-2">
      <div>
        <Label>Logo de l'académie</Label>
        <p className="text-muted-foreground text-xs">
          Il s'affiche en haut à gauche, à côté du nom de votre académie. Il
          est rangé avec vos données, donc il suit vos sauvegardes.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="border-border bg-muted/40 flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-md border">
          {logo ? (
            <img src={logo} alt="" className="size-full object-contain" />
          ) : (
            <ImageUp className="text-muted-foreground size-5" />
          )}
        </span>
        <input
          ref={input}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(event) => {
            chosen(event.target.files?.[0])
            event.target.value = ""
          }}
        />
        <Button size="sm" variant="outline" onClick={() => input.current?.click()}>
          {logo ? "Changer le logo" : "Choisir un logo"}
        </Button>
        {logo && (
          <Button size="sm" variant="ghost" onClick={() => save(null)}>
            <Trash2 className="size-4" />
            Retirer
          </Button>
        )}
      </div>
    </div>
  )
}
