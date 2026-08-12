'use client'

/**
 * Shared dark/light theme state, persisted to localStorage.
 *
 * Both `app/page.tsx` and `app/run/[id]/page.tsx` used to keep their own
 * `useState(true)` for this — meaning every navigation between the list
 * view and a run's detail view (a full route change, so each page mounts
 * fresh) silently reset the theme back to the hardcoded default, even if
 * the user had just switched to light. One shared provider, mounted once
 * in the root layout, is what makes the choice survive navigation.
 */
import { createContext, useContext, useEffect, useState } from 'react'

const STORAGE_KEY = 'scTheme'

type ThemeContextValue = { dark: boolean; toggleTheme: () => void }

const ThemeContext = createContext<ThemeContextValue | null>(null)

// Read synchronously where possible (client-side only) so the first
// render already matches what was saved, instead of flashing dark and
// then flipping to light a tick later.
function readInitialTheme(): boolean {
  if (typeof window === 'undefined') return true
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return stored !== 'light'
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [dark, setDark] = useState(readInitialTheme)

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light')
  }, [dark])

  function toggleTheme() {
    setDark((d) => !d)
  }

  return <ThemeContext.Provider value={{ dark, toggleTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
