import { useSyncExternalStore } from 'react'

/** Whether a CSS media query matches, updating when it changes. */
export function useMediaQuery(query: string) {
  return useSyncExternalStore(
    notify => {
      const m = window.matchMedia(query)
      m.addEventListener('change', notify)
      return () => m.removeEventListener('change', notify)
    },
    () => window.matchMedia(query).matches,
  )
}
