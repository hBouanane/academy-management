// Typed fetch client for the FastAPI backend. All money is integer centimes.

export type Venue = { id: number; name: string }
export type Academy = {
  id: number
  name: string
  venue_bp: number
  owner_bp: number
  venue: Venue | null
  proration_bp: number[]
}
export type Level = { id: number; name: string; teaching_annees: number }
export type Subject = {
  id: number
  name: string
  level_id: number | null
  level_name?: string | null
}
export type Teacher = {
  id: number
  name: string
  phone: string | null
  is_owner: number
}
export type ClassRow = {
  id: number
  name: string
  subject_name: string
  teacher_name: string
  level_name: string
  level_id: number
  subject_id: number
  teacher_id: number
  annee: number | null
  filiere: string | null
  parcours: string | null
  enrolled_count?: number
  is_active: number
}
export type Capability = {
  id: number
  teacher_id: number
  level_id: number
  annee: number | null
  parcours: string | null
  subject_id: number
  subject_name: string
  level_name: string
}
export type TeacherProfileClass = {
  id: number
  name: string
  annee: number | null
  filiere: string | null
  parcours: string | null
  is_active: number
  teacher_id: number
  subject_id: number
  level_id: number
  subject_name: string
  level_name: string
  enrolled_count: number
  earned_centimes: number
}
export type TeacherProfile = Teacher & {
  created_at: string | null
  capabilities: Capability[]
  classes: TeacherProfileClass[]
  history: { month: string; earned: number }[]
  assignments: {
    from_date: string | null
    to_date: string | null
    subject_name: string
    group_name: string
    level_name: string
  }[]
}
export type Package = {
  id: number
  subject_count: number
  monthly_price_centimes: number
  level_id: number | null
  level_name: string | null
  is_active: number
}

export type Motif = { id: number; label: string; is_active: number }

export type HistoryEntry = {
  month: string
  cash_in: number
  enrolled_count: number
  paid_count: number
  unpaid_count: number
}

export type SplitChip = {
  kind: "venue" | "owner" | "teacher"
  ref_id: number
  name: string
  final_centimes: number
}
export type PhoneEntry = { tag: string; number: string }
export type School = { id: number; name: string }
export type Student = {
  id: number
  name: string
  first_name: string | null
  phone: string | null
  level_id: number
  level_name: string
  annee: number | null
  filiere: string | null
  parcours: string | null
  school_name: string | null
  created_at: string | null
  is_active: number
  unpaid_months: number
  month_enrollment_id: number | null
  month_paid: number
  ever_enrolled: number
}
export type ProfileMonth = {
  month: string
  enrollment_id: number
  price_centimes: number
  net_centimes: number
  paid: boolean
  paid_on: string | null
  arrival_date: string | null
  subject_count: number
  subjects: string[]
}
export type StudentProfile = Student & {
  phones: PhoneEntry[]
  months: ProfileMonth[]
}
export type EnrollmentClass = {
  id: number
  subject_name: string
  teacher_name: string
}
export type OverviewEnrollment = {
  id: number
  price_centimes: number
  arrival_date: string | null
  net_centimes: number
  paid: boolean
  payment_id: number | null
  classes: EnrollmentClass[]
  split: SplitChip[]
}
export type OverviewRow = {
  student_id: number
  student_name: string
  level_id: number
  level_name: string
  annee: number | null
  parcours: string | null
  filiere: string | null
  has_arrears: boolean
  enrollment: OverviewEnrollment | null
}

export type PreviewBeneficiary = {
  kind: "venue" | "owner" | "teacher"
  ref_id: number
  name: string
}
export type PreviewLine = PreviewBeneficiary & {
  base_centimes: number
  adjustment_centimes: number
  final_centimes: number
}
export type PreviewAdjustment = {
  id: number
  resolved_centimes: number
  kind: string
  value: number
  category: string
  scope: string
  reason: string | null
  bearers: (PreviewBeneficiary & {
    share_centimes: number
    share_bp: number | null
  })[]
}
export type PaymentPreview = {
  month: string
  price_centimes: number
  net_centimes: number
  lines: PreviewLine[]
  adjustments: PreviewAdjustment[]
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
  last_entry_at: string | null
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

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(detailMessage(body, response.status), response.status)
  }
  return response.json() as Promise<T>
}

function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        (item as { msg?: string }).msg?.replace(/^Value error, /, ""),
      )
      .filter(Boolean)
    if (messages.length) return messages.join(" ; ")
  }
  return `Erreur ${status}`
}

export async function apiGet<T>(url: string): Promise<T> {
  return parse<T>(await fetch(url))
}

export async function apiSend<T>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
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
