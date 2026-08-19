// Recherche tolérante : « bnani » trouve « Bennani », « kh ben » trouve
// « Khadija Bennis », et les accents ne comptent pas. Tout est local — la
// base tient en mémoire, aucun aller-retour réseau.

const normalize = (value: string) =>
  value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim()

/** Tous les caractères de `needle` apparaissent-ils dans l'ordre ? */
const subsequence = (haystack: string, needle: string): boolean => {
  let index = 0
  for (const char of haystack) {
    if (char === needle[index]) index += 1
    if (index === needle.length) return true
  }
  return needle.length === 0
}

/** 0 = aucune correspondance ; plus c'est haut, plus c'est pertinent. */
export function fuzzyScore(text: string, query: string): number {
  const haystack = normalize(text)
  const needle = normalize(query)
  if (!needle) return 1
  if (haystack.startsWith(needle)) return 100
  if (haystack.includes(needle)) return 80
  // Chaque mot de la requête doit toucher un mot du texte (« kh ben »).
  const words = haystack.split(/\s+/)
  const parts = needle.split(/\s+/).filter(Boolean)
  if (
    parts.length > 1 &&
    parts.every((part) => words.some((word) => word.includes(part)))
  )
    return 70
  if (parts.every((part) => words.some((word) => subsequence(word, part))))
    return 40
  return subsequence(haystack, needle) ? 20 : 0
}

/** Filtre + trie une liste selon le texte tapé (vide = liste inchangée). */
export function fuzzyFilter<T>(
  items: T[],
  query: string,
  label: (item: T) => string,
): T[] {
  if (!query.trim()) return items
  return items
    .map((item) => ({ item, score: fuzzyScore(label(item), query) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((entry) => entry.item)
}
