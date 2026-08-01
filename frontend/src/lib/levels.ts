// The Moroccan school ladder: Primaire has 6 années, Collège 3, Lycée 3
// (Tronc commun, 1ère Bac, 2ème Bac — the Bac years carry a filière).

export const anneeOptions = (levelName: string): [string, string][] => {
  if (levelName === "Primaire")
    return Array.from({ length: 6 }, (_, i) => [
      String(i + 1),
      `${i + 1}${i === 0 ? "ère" : "ème"} année`,
    ])
  if (levelName === "Collège")
    return [
      ["1", "1ère année"],
      ["2", "2ème année"],
      ["3", "3ème année"],
    ]
  if (levelName === "Lycée")
    return [
      ["1", "Tronc commun"],
      ["2", "1ère Bac"],
      ["3", "2ème Bac"],
    ]
  return []
}

export const anneeLabel = (
  levelName: string,
  annee: number | null,
): string | null => {
  if (annee === null) return null
  const match = anneeOptions(levelName).find(([value]) => value === String(annee))
  return match ? match[1] : `année ${annee}`
}

export const hasFiliere = (levelName: string, annee: string): boolean =>
  levelName === "Lycée" && (annee === "2" || annee === "3")

// TEACHING granularity: Primaire (one group covers all years) and Formation
// teach as a single block; Collège and Lycée split per année. Students still
// record their année everywhere — this only drives classes and capabilities.
export const teachingAnnees = (levelName: string): [string, string][] =>
  levelName === "Collège" || levelName === "Lycée" ? anneeOptions(levelName) : []

// Parcours: the ministry's new split — programme normal vs râ'ida (back to
// basics) — currently in 3ème année collège. Distinct from filière.
export const parcoursOptions = (levelName: string, annee: string): string[] =>
  levelName === "Collège" && annee === "3" ? ["Normal", "Râ'ida"] : []

export const segmentLabel = (row: {
  level_name: string
  annee: number | null
  parcours: string | null
  filiere: string | null
}): string => {
  const parts = [row.level_name]
  const annee = anneeLabel(row.level_name, row.annee)
  if (annee) parts.push(annee)
  if (row.parcours) parts.push(`parcours ${row.parcours}`)
  if (row.filiere) parts.push(row.filiere)
  return parts.join(" · ")
}

// The ministry's usual branches per Bac year — the dropdown seeds, on top of
// which any filière ever typed in the academy is suggested back.
export const filiereDefaults = (annee: string): string[] => {
  if (annee === "2") return ["Sciences Ex", "Sciences Maths"]
  if (annee === "3") return ["Sciences Physiques", "SVT", "Sciences Maths"]
  return []
}
