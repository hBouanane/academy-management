// GSAP helpers: numbers that count up, marks that grow in.

import { useEffect, useRef } from "react"
import gsap from "gsap"

/** Animates the element's text from 0 to `value`, formatted by `format`. */
export function useCountUp(value: number, format: (n: number) => string) {
  const ref = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    const element = ref.current
    if (!element) return
    element.textContent = format(0)  // visible even before the first rAF tick
    const state = { n: 0 }
    const tween = gsap.to(state, {
      n: value,
      duration: 0.8,
      ease: "power2.out",
      onUpdate: () => {
        element.textContent = format(state.n)
      },
    })
    return () => {
      tween.kill()
    }
  }, [value, format])
  return ref
}

/** Grows children (bars, ring) in with a stagger when `deps` change. */
export function useGrowIn<T extends HTMLElement | SVGElement>(deps: unknown[]) {
  const ref = useRef<T>(null)
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const marks = element.querySelectorAll("[data-grow]")
    if (!marks.length) return
    const tween = gsap.fromTo(
      marks,
      { scaleY: 0, transformOrigin: "bottom" },
      { scaleY: 1, duration: 0.5, ease: "power2.out", stagger: 0.05 },
    )
    return () => {
      tween.kill()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return ref
}
