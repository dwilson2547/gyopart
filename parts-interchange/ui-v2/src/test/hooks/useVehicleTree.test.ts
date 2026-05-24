import { it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useVehicleTree } from '../../hooks/useVehicleTree'
import * as api from '../../lib/api'

vi.mock('../../lib/api')

const years = [{ id: 1, name: '2019' }]
const makes = [{ id: 2, name: 'Honda' }]

beforeEach(() => vi.clearAllMocks())

it('loads years on mount', async () => {
  vi.mocked(api.getYears).mockResolvedValue(years)
  const { result } = renderHook(() => useVehicleTree())
  await waitFor(() => expect(result.current.years).toEqual(years))
})

it('loads makes after year is selected', async () => {
  vi.mocked(api.getYears).mockResolvedValue(years)
  vi.mocked(api.getMakes).mockResolvedValue(makes)
  const { result } = renderHook(() => useVehicleTree())
  await waitFor(() => expect(result.current.years).toHaveLength(1))
  act(() => result.current.selectYear(1, '2019'))
  await waitFor(() => expect(result.current.makes).toEqual(makes))
})

it('resets downstream selections when year changes', async () => {
  vi.mocked(api.getYears).mockResolvedValue(years)
  vi.mocked(api.getMakes).mockResolvedValue(makes)
  const { result } = renderHook(() => useVehicleTree())
  await waitFor(() => expect(result.current.years).toHaveLength(1))
  act(() => result.current.selectYear(1, '2019'))
  await waitFor(() => expect(result.current.makes).toHaveLength(1))
  act(() => result.current.selectYear(1, '2019'))
  expect(result.current.models).toEqual([])
  expect(result.current.trims).toEqual([])
  expect(result.current.engines).toEqual([])
})
