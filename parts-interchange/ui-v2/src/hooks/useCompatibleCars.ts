import { useState, useEffect, useCallback } from 'react'
import { getCompatibleCars } from '../lib/api'
import type { CompatibleCar } from '../types'

export function useCompatibleCars(partId: number | null) {
  const [cars, setCars] = useState<CompatibleCar[]>([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [page, setPage] = useState(0)
  const [sortCol, setSortCol] = useState('')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [filterStr, setFilterStr] = useState('')
  const [loading, setLoading] = useState(false)

  const fetch = useCallback(async (opts: { pageNum: number; col: string; dir: 'asc' | 'desc'; filter: string; append: boolean }) => {
    if (!partId) return
    setLoading(true)
    try {
      const data = await getCompatibleCars(partId, { part_id: partId, page: opts.pageNum, per_page: 30, sort_col: opts.col, sort_dir: opts.dir, filterStr: opts.filter })
      setCars(prev => opts.append ? [...prev, ...data.items] : data.items)
      setTotal(data.total)
      setHasMore(data.has_next)
      setPage(opts.pageNum)
    } finally {
      setLoading(false)
    }
  }, [partId])

  useEffect(() => {
    setCars([])
    setPage(0)
    if (partId) fetch({ pageNum: 0, col: sortCol, dir: sortDir, filter: filterStr, append: false })
  // Intentional: re-fetch on partId change using current sort/filter state.
  // fetch() reads sortCol/sortDir/filterStr from the live closure, not a stale snapshot.
  }, [partId]) // eslint-disable-line react-hooks/exhaustive-deps

  function setSort(col: string, dir: 'asc' | 'desc') {
    setSortCol(col); setSortDir(dir)
    fetch({ pageNum: 0, col, dir, filter: filterStr, append: false })
  }

  function setFilter(val: string) {
    setFilterStr(val)
    fetch({ pageNum: 0, col: sortCol, dir: sortDir, filter: val, append: false })
  }

  function loadMore() {
    if (hasMore && !loading) fetch({ pageNum: page + 1, col: sortCol, dir: sortDir, filter: filterStr, append: true })
  }

  return { cars, total, hasMore, loading, sortCol, sortDir, filterStr, setSort, setFilter, loadMore }
}
