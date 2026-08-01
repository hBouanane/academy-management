// What a professor CAN teach: the niveau → année → (parcours) → matière tree
// with checkboxes at the leaves. Ticking a branch ticks all its leaves.

import { useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Notice } from "@/components/Notice"
import { apiGet, apiSend } from "@/lib/api"
import type { Capability, Level, Subject } from "@/lib/api"
import { parcoursOptions, teachingAnnees } from "@/lib/levels"

type Leaf = {
  level_id: number
  annee: number | null
  parcours: string | null
  subject_id: number
}

const leafKey = (leaf: Leaf) =>
  `${leaf.level_id}|${leaf.annee ?? ""}|${leaf.parcours ?? ""}|${leaf.subject_id}`

type Branch = { label: string; annee: number | null; parcours: string | null }

// Primaire and Formation teach as one block; Collège/Lycée branch per année,
// and 3ème collège forks into its two parcours.
const branches = (levelName: string): Branch[] => {
  const annees = teachingAnnees(levelName)
  if (annees.length === 0)
    return [{ label: "Toutes années", annee: null, parcours: null }]
  return annees.flatMap(([value, label]): Branch[] => {
    const parcours = parcoursOptions(levelName, value)
    if (parcours.length === 0)
      return [{ label, annee: Number(value), parcours: null }]
    return parcours.map((option) => ({
      label: `${label} — ${option}`,
      annee: Number(value),
      parcours: option,
    }))
  })
}

type Props = {
  teacherId: number | null
  teacherName: string
  onClose: () => void
  onSaved?: () => void
}

export function CapabilityTree({ teacherId, teacherName, onClose, onSaved }: Props) {
  const [levels, setLevels] = useState<Level[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (teacherId === null) return
    setError(null)
    apiGet<Level[]>("/api/levels").then(setLevels).catch(() => {})
    apiGet<Subject[]>("/api/subjects").then(setSubjects).catch(() => {})
    apiGet<Capability[]>("/api/capabilities")
      .then((rows) =>
        setChecked(
          new Set(
            rows
              .filter((row) => row.teacher_id === teacherId)
              .map((row) =>
                leafKey({
                  level_id: row.level_id,
                  annee: row.annee,
                  parcours: row.parcours,
                  subject_id: row.subject_id,
                }),
              ),
          ),
        ),
      )
      .catch((err: Error) => setError(err.message))
  }, [teacherId])

  const tree = useMemo(
    () =>
      levels.map((level) => ({
        level,
        branches: branches(level.name).map((branch) => ({
          branch,
          leaves: subjects.map((subject) => ({
            level_id: level.id,
            annee: branch.annee,
            parcours: branch.parcours,
            subject_id: subject.id,
          })),
        })),
      })),
    [levels, subjects],
  )

  const toggle = (keys: string[], on: boolean) =>
    setChecked((current) => {
      const next = new Set(current)
      for (const key of keys) {
        if (on) next.add(key)
        else next.delete(key)
      }
      return next
    })

  const save = () => {
    setBusy(true)
    const items = tree
      .flatMap((node) => node.branches)
      .flatMap((branch) => branch.leaves)
      .filter((leaf) => checked.has(leafKey(leaf)))
    apiSend("PUT", `/api/teachers/${teacherId}/capabilities`, { items })
      .then(() => {
        onSaved?.()
        onClose()
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false))
  }

  return (
    <Dialog open={teacherId !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-x-hidden overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Compétences — {teacherName}</DialogTitle>
        </DialogHeader>
        <p className="text-muted-foreground text-sm">
          Cochez ce que ce professeur peut enseigner — les classes qu'il enseigne
          déjà se cochent toutes seules.
        </p>
        <Notice message={error} />
        {subjects.length === 0 && (
          <p className="text-muted-foreground text-sm">
            Aucune matière pour l'instant — elles apparaîtront ici dès la
            première classe créée.
          </p>
        )}
        <div className="space-y-4">
          {tree.map(({ level, branches: levelBranches }) => (
            <div key={level.id}>
              <p className="mb-1.5 text-sm font-semibold">{level.name}</p>
              <div className="space-y-2 pl-3">
                {levelBranches.map(({ branch, leaves }) => {
                  const keys = leaves.map(leafKey)
                  const all = keys.length > 0 && keys.every((k) => checked.has(k))
                  return (
                    <div key={branch.label}>
                      <label className="flex items-center gap-2 text-sm font-medium">
                        <Checkbox
                          checked={all}
                          onCheckedChange={(state) => toggle(keys, state === true)}
                        />
                        {branch.label}
                      </label>
                      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 pl-6">
                        {leaves.map((leaf) => {
                          const key = leafKey(leaf)
                          const subject = subjects.find(
                            (s) => s.id === leaf.subject_id,
                          )
                          return (
                            <label
                              key={key}
                              className="text-muted-foreground flex items-center gap-1.5 text-sm"
                            >
                              <Checkbox
                                checked={checked.has(key)}
                                onCheckedChange={(state) =>
                                  toggle([key], state === true)
                                }
                              />
                              {subject?.name}
                            </label>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button onClick={save} disabled={busy}>
            {busy ? "…" : "Enregistrer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
