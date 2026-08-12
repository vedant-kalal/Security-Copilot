'use client'

import { useEffect, useState } from 'react'

/**
 * A score bar that animates its fill in from 0 on mount (or whenever the
 * score changes) instead of just appearing already at its final width.
 * globals.css already puts a `transition: width` on .score-mini-fill —
 * that only has something to animate *from* if the width actually
 * changes after the first paint, so this starts at 0 and bumps to the
 * real value one animation frame later, giving the browser a paint in
 * between to interpolate from. Shared by the table rows (page.tsx) and
 * the run detail page's own score bar so both fill in the same way.
 */
export function ScoreBar({ score, color, className }: { score: number; color: string; className?: string }) {
  const [width, setWidth] = useState(0)

  useEffect(() => {
    setWidth(0)
    const raf = requestAnimationFrame(() => setWidth(score))
    return () => cancelAnimationFrame(raf)
  }, [score])

  return (
    <span className={className ? `score-mini-bar ${className}` : 'score-mini-bar'}>
      <span className="score-mini-fill" style={{ width: `${width}%`, background: color }} />
    </span>
  )
}
