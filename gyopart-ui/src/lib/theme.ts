import { useEffect, useState } from 'react'

export type ThemeMode = 'system' | 'light' | 'dark'

const KEY = 'gyopart-theme' // also read by the boot script in index.html
const ORDER: ThemeMode[] = ['system', 'light', 'dark']
const media = window.matchMedia('(prefers-color-scheme: dark)')

function saved(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY) as ThemeMode | null
    return v && ORDER.includes(v) ? v : 'system'
  } catch {
    return 'system'
  }
}

function apply(mode: ThemeMode) {
  const dark = mode === 'dark' || (mode === 'system' && media.matches)
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
}

/** System → Light → Dark → System, like photo-dump. "system" follows the device setting live. */
export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(saved)
  useEffect(() => {
    apply(mode)
    const onChange = () => apply(mode)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [mode])
  const cycle = () => {
    const next = ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length]
    try { localStorage.setItem(KEY, next) } catch { /* storage unavailable */ }
    setMode(next)
  }
  return { mode, cycle }
}
