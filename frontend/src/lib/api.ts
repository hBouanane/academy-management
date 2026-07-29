// Typed fetch client for the FastAPI backend. All money is integer centimes.

export type Venue = { id: number; name: string }
export type Academy = {
  id: number
  name: string
  venue_bp: number
  owner_bp: number
  venue: Venue | null
}
export type Level = { id: number; name: string }
export type Subject = { id: number; name: string }
export type Teacher = { id: number; name: string; phone: string | null }
export type ClassRow = {
  id: number
  name: string
  subject_name: string
  teacher_name: string
  level_name: string
  level_id: number
  subject_id: number
  teacher_id: number
}
export type Package = {
  id: number
  subject_count: number
  monthly_price_centimes: number
}
export type Student = {
  id: number
  name: string
  phone: string | null
  level_id: number
  level_name: string
  is_active: number
}
export type EnrollmentClass = {
  id: number
  subject_name: string
  teacher_name: string
}
export type OverviewEnrollment = {
  id: number
  price_centimes: number
  net_centimes: number
  paid: boolean
  payment_id: number | null
  classes: EnrollmentClass[]
}
export type OverviewRow = {
  student_id: number
  student_name: string
  level_name: string
  enrollment: OverviewEnrollment | null
}
export type BeneficiaryTotal = {
  kind: "venue" | "owner" | "teacher"
  ref_id: number
  name: string
  total: number
}
export type MonthlyReport = {
  month: string
  cash_in: number
  totals: BeneficiaryTotal[]
  by_level: { level_id: number; level_name: string; totals: BeneficiaryTotal[] }[]
}
export type ArrearsEntry = {
  student_id: number
  student_name: string
  level_name: string
  total_owed: number
  items: { enrollment_id: number; month: string; owed: number }[]
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(detailMessage(body, response.status))
  }
  return response.json() as Promise<T>
}

function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item as { msg?: string }).msg)
      .filter(Boolean)
    if (messages.length) return messages.join(" ; ")
  }
  return `Erreur ${status}`
}

export async function apiGet<T>(url: string): Promise<T> {
  return parse<T>(await fetch(url))
}

export async function apiSend<T>(
  method: "POST" | "PATCH" | "DELETE",
  url: string,
  body?: unknown,
): Promise<T> {
  return parse<T>(
    await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  )
}
