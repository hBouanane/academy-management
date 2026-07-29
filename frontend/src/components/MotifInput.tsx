import { useEffect, useState } from "react"
import { Input } from "@/components/ui/input"
import { apiGet, apiSend } from "@/lib/api"

type Motif = { id: number; label: string }

/** Reusable reasons: free text over a datalist of saved motifs. `ensure()`
    persists a new label so it appears in the list next time. */
export function useMotifs() {
  const [motifs, setMotifs] = useState<Motif[]>([])

  const reload = () => {
    apiGet<Motif[]>("/api/motifs").then(setMotifs).catch(() => {})
  }
  useEffect(reload, [])

  const ensure = async (label: string) => {
    const trimmed = label.trim()
    if (!trimmed) return
    if (motifs.some((motif) => motif.label === trimmed)) return
    await apiSend("POST", "/api/motifs", { label: trimmed }).catch(() => {})
    reload()
  }

  return { motifs, ensure }
}

export function MotifInput({
  value,
  onChange,
  motifs,
}: {
  value: string
  onChange: (value: string) => void
  motifs: Motif[]
}) {
  return (
    <>
      <Input
        list="motif-options"
        placeholder="Motif (choisir ou saisir un nouveau)"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <datalist id="motif-options">
        {motifs.map((motif) => (
          <option key={motif.id} value={motif.label} />
        ))}
      </datalist>
    </>
  )
}
