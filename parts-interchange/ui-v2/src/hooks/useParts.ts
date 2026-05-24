import { useState, useEffect, useCallback, useRef } from 'react'
import { getParts } from '../lib/api'
import type { Part } from '../types'

export function useParts(carId: number | null) {
  const [parts, setParts] = useState<Part[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [page, setPage] = useState(0)
  const [filter, setFilterStr] = useState('')
  const [loading, setLoading] = useState(false)
  const filterRef = useRef(filter)
  filterRef.current = filter

  const fetchPage = useCallback(async (pageNum: number, filterStr: string, append: boolean) => {
    if (!carId) return
    setLoading(true)
    try {
      const data = await getParts({ car_id: carId, page: pageNum, per_page: 30, sort_col: '', sort_dir: 'desc', filterStr })
      setParts(prev => append ? [...prev, ...data.items] : data.items)
      setHasMore(data.has_next)
      setPage(pageNum)
    } finally {
      setLoading(false)
    }
  }, [carId])

  useEffect(() => {
    setParts([])
    setPage(0)
    if (carId) fetchPage(0, filterRef.current, false)
  }, [carId, fetchPage])

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [])

  function setFilter(val: string) {
    setFilterStr(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => fetchPage(0, val, false), 300)
  }

  function loadMore() {
    if (hasMore && !loading) fetchPage(page + 1, filterRef.current, true)
  }

  return { parts, hasMore, loading, filter, setFilter, loadMore }
}
