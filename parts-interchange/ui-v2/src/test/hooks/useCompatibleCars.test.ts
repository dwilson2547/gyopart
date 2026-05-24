import { it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useCompatibleCars } from '../../hooks/useCompatibleCars'
import * as api from '../../lib/api'
import type { ApiPage, CompatibleCar } from '../../types'

vi.mock('../../lib/api')

const page1 = {
  items: [{ id: 10, year: { name: '2018' }, make: { name: 'Toyota' }, model: { name: 'Camry' }, trim: { name: 'LE' }, engine: { name: '2.5L' } }],
  total: 1, page: 1, per_page: 30, pages: 1, has_next: false, has_prev: false,
} as unknown as ApiPage<CompatibleCar>

beforeEach(() => vi.clearAllMocks())

it('fetches on partId change', async () => {
  vi.mocked(api.getCompatibleCars).mockResolvedValue(page1)
  const { result } = renderHook(() => useCompatibleCars(5))
  await waitFor(() => expect(result.current.cars).toHaveLength(1))
  expect(api.getCompatibleCars).toHaveBeenCalledWith(5, expect.objectContaining({ part_id: 5, page: 0 }))
})

it('resets to page 0 on sort change', async () => {
  vi.mocked(api.getCompatibleCars).mockResolvedValue(page1)
  const { result } = renderHook(() => useCompatibleCars(5))
  await waitFor(() => expect(result.current.cars).toHaveLength(1))
  act(() => result.current.setSort('year', 'asc'))
  await waitFor(() => expect(api.getCompatibleCars).toHaveBeenLastCalledWith(5, expect.objectContaining({ page: 0, sort_col: 'year', sort_dir: 'asc' })))
})
