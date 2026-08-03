// A labeled fact: what it is on top, the value below. Profiles are made of
// these instead of anonymous tag soups.

export function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="min-w-0">
      <p className="text-muted-foreground text-xs">{label}</p>
      <div className="text-sm font-medium">{children}</div>
    </div>
  )
}

export function FieldGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="border-border grid grid-cols-2 gap-x-4 gap-y-3 rounded-xl border p-4 sm:grid-cols-3">
      {children}
    </div>
  )
}
