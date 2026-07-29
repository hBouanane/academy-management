// GSAP helpers: numbers that count up, marks that grow in.

import { useEffect, useRef } from "react"
import gsap from "gsap"

/** Animates the element's text from 0 to `value`, formatted by `format`. */
export function useCountUp(value: number, format: (n: number) => string) {
  const ref = useRef<HTMLSpanElement>(null)
  // Keep the formatter out of the effect deps: a fresh arrow function on each
  // parent render must not restart the animation (e.g. while typing a search).
  const formatRef = useRef(format)
  formatRef.current = format
  useEffect(() => {
    const element = ref.current
    if (!element) return
    element.textContent = formatRef.current(0) // visible before the first rAF tick
    const state = { n: 0 }
    const tween = gsap.to(state, {
      n: value,
      duration: 0.8,
      ease: "power2.out",
      onUpdate: () => {
        element.textContent = formatRef.current(state.n)
      },
    })
    return () => {
      tween.kill()
    }
  }, [value])
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
