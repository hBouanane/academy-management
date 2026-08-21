export function formatDH(centimes: number): string {
  const dirhams = centimes / 100
  return `${dirhams.toLocaleString("fr-MA", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} DH`
}

export function dhToCentimes(dirhams: string): number {
  return Math.round(Number(dirhams.replace(",", ".")) * 100)
}

/** From centimes to what one types in a field: « 180 », « 180,50 ». No
    « DH » and no spaces -- this is a value, not a display. */
export function centimesToDh(centimes: number): string {
  const dirhams = centimes / 100
  return Number.isInteger(dirhams)
    ? String(dirhams)
    : dirhams.toFixed(2).replace(".", ",")
}

export function previousMonth(month: string): string {
  const [year, monthNumber] = month.split("-").map(Number)
  const date = new Date(year, monthNumber - 2, 1)
  const paddedMonth = String(date.getMonth() + 1).padStart(2, "0")
  return `${date.getFullYear()}-${paddedMonth}`
}

export function currentMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`
}
