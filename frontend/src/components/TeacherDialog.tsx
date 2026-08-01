// The front door of the whole flow: create (or edit) a professor and, right
// below his identity, THE TREE of what he can teach — checkbox chips per
// niveau/année/parcours, growable in place.

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Notice } from "@/components/Notice"
import { ProgramTree, slotKey } from "@/components/ProgramTree"
import { apiGet, apiSend } from "@/lib/api"
import type { Capability, Level, Subject, Teacher } from "@/lib/api"

const phoneDigits = (value: string) => value.replace(/[\s.-]/g, "")

const parseKey = (key: string) => {
  const [level, annee, parcours, subject] = key.split("|")
  return {
    level_id: Number(level),
    annee: annee === "" ? null : Number(annee),
    parcours: parcours === "" ? null : parcours,
    subject_id: Number(subject),
  }
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  initial?: Teacher | null
  onSaved: () => void
}

export function TeacherDialog({ open, onOpenChange, initial, onSaved }: Props) {
  const [name, setName] = useState("")
  const [phone, setPhone] = useState("")
  const [isOwner, setIsOwner] = useState("0")
  const [levels, setLevels] = useState<Level[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const loadTree = () => {
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
    apiGet<Subject[]>("/api/subjects").then(setSubjects).catch(() => {})
  }

  useEffect(() => {
    if (!open) return
    setName(initial?.name ?? "")
    setPhone(initial?.phone ?? "")
    setIsOwner(initial?.is_owner ? "1" : "0")
    setChecked(new Set())
    setNote(null)
    setBusy(false)
    loadTree()
    if (initial) {
      apiGet<Capability[]>("/api/capabilities")
        .then((rows) =>
          setChecked(
            new Set(
              rows
                .filter((row) => row.teacher_id === initial.id)
                .map((row) =>
                  slotKey(
                    {
                      level_id: row.level_id,
                      annee: row.annee,
                      parcours: row.parcours,
                    },
                    row.subject_id,
                  ),
                ),
            ),
          ),
        )
        .catch(() => {})
    }
  }, [open, initial])

  const toggle = (slots: { key: string }[], on: boolean) =>
    setChecked((current) => {
      const next = new Set(current)
      for (const slot of slots) {
        if (on) next.add(slot.key)
        else next.delete(slot.key)
      }
      return next
    })

  const submit = async () => {
    if (!name.trim()) {
      setNote("Le nom est obligatoire.")
      return
    }
    if (phone && !/^\d{10}$/.test(phoneDigits(phone))) {
      setNote("Le téléphone doit contenir exactement 10 chiffres.")
      return
    }
    setNote(null)
    setBusy(true)
    try {
      let teacherId = initial?.id
      if (initial) {
        await apiSend("PATCH", `/api/teachers/${initial.id}`, {
          name: name.trim(),
          phone: phoneDigits(phone),
          ...(isOwner === "1" && !initial.is_owner ? { is_owner: true } : {}),
        })
      } else {
        teacherId = (
          await apiSend<{ id: number }>("POST", "/api/teachers", {
            name: name.trim(),
            phone: phoneDigits(phone) || null,
          })
        ).id
      }
      await apiSend("PUT", `/api/teachers/${teacherId}/capabilities`, {
        items: [...checked].map(parseKey),
      })
      onOpenChange(false)
      onSaved()
    } catch (err) {
      setNote((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {initial ? `Modifier ${initial.name}` : "Nouveau professeur"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <div className="min-w-40 flex-1 space-y-2">
              <Label>Nom</Label>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Ahmed Benali"
              />
            </div>
            <div className="min-w-40 flex-1 space-y-2">
              <Label>
                Téléphone <span className="text-muted-foreground">(optionnel)</span>
              </Label>
              <Input
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                placeholder="06…"
              />
            </div>
            {initial && (
              <div className="min-w-40 flex-1 space-y-2">
                <Label>Propriétaire ?</Label>
                <Select value={isOwner} onValueChange={setIsOwner}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">Non</SelectItem>
                    <SelectItem value="1">Oui — cumul dans les rapports</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <div>
            <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
              Ce qu'il peut enseigner — cochez dans l'arbre
            </p>
            <ProgramTree
              levels={levels}
              subjects={subjects}
              checked={checked}
              onToggle={toggle}
              onGrown={loadTree}
            />
          </div>

          <Notice message={note} />
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={busy}>
            {busy ? "…" : initial ? "Enregistrer" : "Créer le professeur"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
