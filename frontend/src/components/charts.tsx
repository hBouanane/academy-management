// Dashboard charts: plain SVG, one validated hue per mode (--chart-mark),
// GSAP grow-ins, hover tooltips. Single series -> no legend (title names it).

import { useEffect, useRef, useState } from "react"
import gsap from "gsap"
import { useGrowIn } from "@/lib/anim"
import { formatDH } from "@/lib/money"

type HistoryEntry = {
  month: string
  cash_in: number
  enrolled_count: number
  paid_count: number
  unpaid_count: number
}

export function CashBars({ history }: { history: HistoryEntry[] }) {
  const ref = useGrowIn<HTMLDivElement>([history])
  const [hover, setHover] = useState<HistoryEntry | null>(null)
  const max = Math.max(...history.map((entry) => entry.cash_in), 1)

  return (
    <div ref={ref} className="space-y-2">
      <div className="flex h-36 items-end gap-2">
        {history.map((entry) => (
          <div
            key={entry.month}
            className="group flex h-full flex-1 cursor-default flex-col justify-end"
            onMouseEnter={() => setHover(entry)}
            onMouseLeave={() => setHover(null)}
          >
            <div
              data-grow
              className="w-full rounded-t-[4px] transition-opacity group-hover:opacity-80"
              style={{
                height: `${Math.max((entry.cash_in / max) * 100, 2)}%`,
                background: "var(--chart-mark)",
              }}
            />
          </div>
        ))}
      </div>
      <div className="text-muted-foreground flex gap-2 text-[11px]">
        {history.map((entry) => (
          <span key={entry.month} className="flex-1 text-center">
            {entry.month.slice(5)}
          </span>
        ))}
      </div>
      <p className="text-muted-foreground h-4 text-xs">
        {hover
          ? `${hover.month} : ${formatDH(hover.cash_in)} encaissés · ${hover.paid_count}/${hover.enrolled_count} payés`
          : " "}
      </p>
    </div>
  )
}

/** Collection-rate ring — stroke color slides red → green with the ratio. */
export function CollectionRing({
  paid,
  total,
}: {
  paid: number
  total: number
}) {
  const empty = total === 0
  const ratio = empty ? 0 : paid / total
  const circleRef = useRef<SVGCircleElement>(null)
  const radius = 42
  const circumference = 2 * Math.PI * radius

  useEffect(() => {
    const circle = circleRef.current
    if (!circle) return
    const tween = gsap.fromTo(
      circle,
      { strokeDashoffset: circumference },
      {
        strokeDashoffset: circumference * (1 - ratio),
        duration: 0.9,
        ease: "power2.out",
      },
    )
    return () => {
      tween.kill()
    }
  }, [ratio, circumference])

  // color-mix keeps both endpoints theme-aware (destructive -> success).
  const stroke = empty
    ? "var(--border-strong)"
    : `color-mix(in oklch, var(--success) ${Math.round(ratio * 100)}%, var(--destructive))`

  return (
    <div className="flex items-center gap-4">
      <svg width="104" height="104" viewBox="0 0 104 104" role="img" aria-label={`Part déjà payée ${Math.round(ratio * 100)}%`}>
        <circle
          cx="52"
          cy="52"
          r={radius}
          fill="none"
          stroke="var(--border)"
          strokeWidth="8"
        />
        <circle
          ref={circleRef}
          cx="52"
          cy="52"
          r={radius}
          fill="none"
          stroke={stroke}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference}
          transform="rotate(-90 52 52)"
        />
        <text
          x="52"
          y="57"
          textAnchor="middle"
          className="fill-foreground text-lg font-semibold"
        >
          {empty ? "—" : `${Math.round(ratio * 100)}%`}
        </text>
      </svg>
      <div className="text-sm">
        <p className="font-medium">Part déjà payée</p>
        <p className="text-muted-foreground">
          {paid} payé(s) sur {total} inscrit(s)
        </p>
      </div>
    </div>
  )
}
