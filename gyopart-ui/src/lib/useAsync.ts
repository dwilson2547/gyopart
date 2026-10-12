import { useCallback, useEffect, useState } from 'react'
import { errorMessage } from '../api'

interface Result<T> { key: string; data: T | null; error: string | null }

/** Run `fn` whenever `deps` change (skipped while `enabled` is false). Stale responses are dropped. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[], enabled = true) {
  const [nonce, setNonce] = useState(0)
  const [result, setResult] = useState<Result<T> | null>(null)
  const key = JSON.stringify([deps, nonce])

  useEffect(() => {
    if (!enabled) return
    let live = true
    fn()
      .then(data => { if (live) setResult({ key, data, error: null }) })
      .catch(e => { if (live) setResult({ key, data: null, error: errorMessage(e) }) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled])

  const retry = useCallback(() => setNonce(n => n + 1), [])
  const current = enabled && result?.key === key ? result : null
  return {
    data: current?.data ?? null,
    error: current?.error ?? null,
    loading: enabled && !current,
    retry,
  }
}
