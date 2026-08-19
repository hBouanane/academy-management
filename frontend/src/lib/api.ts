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
  // null = « Sans professeur » : the class survives while a replacement is
  // sought; vacant days escrow the teacher share to the académie.
  teacher_name: string | null
  level_name: string
  level_id: number
  subject_id: number
  teacher_id: number | null
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
  owner_earned: number
  capabilities: Capability[]
  classes: TeacherProfileClass[]
  history: { month: string; earned: number }[]
  assignments: {
    from_date: string | null
    to_date: string | null
    subject_name: string
    level_name: string
  }[]
}
export type Package = {
  id: number
  subject_count: number
  monthly_price_centimes: number
  level_id: number | null
  level_name: string | null
  // Price variants (bloc niveaux): the price point's name — not a reduction.
  label: string | null
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
  month_remaining_centimes: number // > 0 with month_paid = an avance
  ever_enrolled: number
}
export type ProfileMonth = {
  month: string
  enrollment_id: number
  price_centimes: number
  net_centimes: number
  paid: boolean
  paid_on: string | null
  payment_id: number | null
  remaining_centimes: number // > 0 = avance still to complete
  arrival_date: string | null
  subject_count: number
  subjects: string[]
  refund_pending_centimes: number
  refunded_centimes: number
}
export type ClassShare = {
  class_id: number
  month: string
  /** true = le propriétaire a fixé les parts lui-même. */
  manual: boolean
  days_in_month: number
  shares: {
    teacher_id: number
    teacher_name: string
    days: number
    share_bp: number
  }[]
}
export type ClassProfile = ClassRow & {
  enrolled_count: number
  students: {
    student_id: number
    student_name: string
    first_name: string | null
    enrollment_id: number
    paid: number
  }[]
  assignments: {
    teacher_name: string
    from_date: string | null
    to_date: string | null
  }[]
}
export type StudentProfile = Student & {
  phones: PhoneEntry[]
  months: ProfileMonth[]
}
export type EnrollmentClass = {
  id: number
  subject_name: string
  teacher_name: string | null
}
export type OverviewEnrollment = {
  id: number
  price_centimes: number
  arrival_date: string | null
  net_centimes: number
  paid: boolean
  payment_id: number | null
  remaining_centimes: number // > 0 = avance still to complete
  // Unpaid month whose professors the académie already paid out of pocket.
  guaranteed_centimes: number
  stopped: boolean
  // Classe archivée sous un élève qui avait payé : il attend son argent.
  refund_pending_centimes: number
  refunded_centimes: number
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
  recurring: number
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
export type Refund = {
  id: number
  enrollment_id: number
  class_id: number
  student_id: number
  student_name: string
  first_name: string | null
  subject_name: string
  level_name: string
  month: string
  percent_bp: number
  amount_centimes: number
  status: "pending" | "settled"
  created_at: string
  settled_at: string | null
}
export type Payout = {
  id: number
  amount_centimes: number
  paid_on: string
  note: string | null
}
export type OverpaidCharge = {
  id: number
  amount_centimes: number
  created_at: string
  note: string | null
}
export type CaisseLine = {
  kind: "teacher" | "venue" | "owner"
  ref_id: number
  name: string
  is_owner: number
  due_centimes: number // négatif = ce bénéficiaire a avancé de sa poche
  paid_centimes: number
  remaining_centimes: number
  // Versé de plus que le dû — une réduction ou un remboursement est passé
  // après le versement. À déduire plus tard, jamais repris tout seul.
  overpaid_centimes: number
  previous_overpaid_centimes: number
  // Le trop-versé que l'academie a assume : le beneficiaire garde
  // l'argent, le rappel s'eteint, la trace reste.
  charged_centimes: number
  charges: OverpaidCharge[]
  payouts: Payout[]
}
export type Caisse = {
  month: string
  collected_centimes: number
  paid_out_centimes: number
  balance_centimes: number
  unpaid_centimes: number
  projection: { venue_centimes: number; owner_centimes: number }
  lines: CaisseLine[]
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

// Le jeton de session vit en mémoire, jamais sur le disque : fermer
// l'application referme le verrou, et rien ne traîne pour demain matin.
let sessionToken: string | null = null
// Prévenu quand le serveur répond « verrouillée » — l'écran de
// déverrouillage remonte alors de lui-même, sans qu'on ait à recharger.
let onLocked: (() => void) | null = null

export function setSessionToken(token: string | null) {
  sessionToken = token
}

export function whenLocked(handler: () => void) {
  onLocked = handler
}

function authHeaders(base: Record<string, string> = {}): Record<string, string> {
  return sessionToken ? { ...base, "X-Session-Token": sessionToken } : base
}

async function guard<T>(response: Response): Promise<T> {
  if (response.status === 401 && !response.url.includes("/api/lock")) {
    sessionToken = null
    onLocked?.()
  }
  return parse<T>(response)
}

export async function apiGet<T>(url: string): Promise<T> {
  return guard<T>(await fetch(url, { headers: authHeaders() }))
}

export async function apiSend<T>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  url: string,
  body?: unknown,
): Promise<T> {
  return guard<T>(
    await fetch(url, {
      method,
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  )
}

export type StaleDocument = {
  kind: "payslip" | "absence" | "excel"
  month: string
  scope: string
  ref_id: number
  path: string
  generated_at: string
  touched_at: string
  label: string
}

export type Folders = {
  documents: { path: string | null; example: string | null }
  database: { path: string | null }
}

export type LockState = {
  configured: boolean
  auto_lock_minutes: number
  unlocked: boolean
}
