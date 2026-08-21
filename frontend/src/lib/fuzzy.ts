// Forgiving search: « bnani » finds « Bennani », « kh ben » finds
// « Khadija Bennis », and accents do not count. Everything is local -- the
// database fits in memory, with no network round-trip.

const normalize = (value: string) =>
  value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim()

/** Do all of `needle`'s characters appear, in order? */
const subsequence = (haystack: string, needle: string): boolean => {
  let index = 0
  for (const char of haystack) {
    if (char === needle[index]) index += 1
    if (index === needle.length) return true
  }
  return needle.length === 0
}

/** 0 = no match; the higher it goes, the more relevant. */
export function fuzzyScore(text: string, query: string): number {
  const haystack = normalize(text)
  const needle = normalize(query)
  if (!needle) return 1
  if (haystack.startsWith(needle)) return 100
  if (haystack.includes(needle)) return 80
  // Every word of the query must hit a word of the text (« kh ben »).
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

/** Filters and sorts a list by the typed text (empty = list unchanged). */
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
