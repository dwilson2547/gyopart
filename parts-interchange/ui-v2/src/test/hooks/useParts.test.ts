import { it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useParts } from '../../hooks/useParts'
import * as api from '../../lib/api'
import type { ApiPage, Part } from '../../types'

vi.mock('../../lib/api')

const page1 = { items: [{ id: 1, part_number: 'ABC', title: 'Widget', images: [] }], total: 2, page: 1, per_page: 30, pages: 2, has_next: true, has_prev: false } as unknown as ApiPage<Part>
const page2 = { items: [{ id: 2, part_number: 'DEF', title: 'Gadget', images: [] }], total: 2, page: 2, per_page: 30, pages: 2, has_next: false, has_prev: true } as unknown as ApiPage<Part>

beforeEach(() => vi.clearAllMocks())

it('fetches first page on carId change', async () => {
  vi.mocked(api.getParts).mockResolvedValue(page1)
  const { result } = renderHook(() => useParts(1))
  await waitFor(() => expect(result.current.parts).toHaveLength(1))
  expect(api.getParts).toHaveBeenCalledWith(expect.objectContaining({ car_id: 1, page: 0 }))
})

it('appends items on loadMore', async () => {
  vi.mocked(api.getParts).mockResolvedValueOnce(page1).mockResolvedValueOnce(page2)
  const { result } = renderHook(() => useParts(1))
  await waitFor(() => expect(result.current.parts).toHaveLength(1))
  act(() => result.current.loadMore())
  await waitFor(() => expect(result.current.parts).toHaveLength(2))
})

it('resets to page 0 when filter changes', async () => {
  vi.mocked(api.getParts).mockResolvedValue(page1)
  const { result } = renderHook(() => useParts(1))
  await waitFor(() => expect(result.current.parts).toHaveLength(1))
  act(() => result.current.setFilter('brake'))
  await waitFor(() => expect(api.getParts).toHaveBeenLastCalledWith(expect.objectContaining({ page: 0, filterStr: 'brake' })), { timeout: 500 })
})
