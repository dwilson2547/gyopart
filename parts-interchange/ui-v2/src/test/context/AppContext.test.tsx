import { it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { AppProvider, useApp } from '../../context/AppContext'
import type { ActiveCar, Part } from '../../types'

beforeEach(() => localStorage.clear())

const car: ActiveCar = { id: 1, year: '2019', make: 'Honda', model: 'Civic', trim: 'EX', engine: '1.5T' }
const part = { id: 42 } as Part

function wrapper({ children }: { children: React.ReactNode }) {
  return <AppProvider>{children}</AppProvider>
}

it('starts with null activeCar and activePart, garage from localStorage', () => {
  const { result } = renderHook(() => useApp(), { wrapper })
  expect(result.current.state.activeCar).toBeNull()
  expect(result.current.state.activePart).toBeNull()
  expect(result.current.state.garage).toEqual([])
})

it('SET_ACTIVE_CAR sets car and clears activePart', () => {
  const { result } = renderHook(() => useApp(), { wrapper })
  act(() => result.current.dispatch({ type: 'SET_ACTIVE_PART', payload: part }))
  act(() => result.current.dispatch({ type: 'SET_ACTIVE_CAR', payload: car }))
  expect(result.current.state.activeCar).toEqual(car)
  expect(result.current.state.activePart).toBeNull()
})

it('ADD_TO_GARAGE persists to localStorage', () => {
  const { result } = renderHook(() => useApp(), { wrapper })
  act(() => result.current.dispatch({ type: 'ADD_TO_GARAGE', payload: car }))
  expect(result.current.state.garage).toHaveLength(1)
  expect(JSON.parse(localStorage.getItem('pi_garage')!)).toHaveLength(1)
})

it('ADD_TO_GARAGE does not add duplicates', () => {
  const { result } = renderHook(() => useApp(), { wrapper })
  act(() => result.current.dispatch({ type: 'ADD_TO_GARAGE', payload: car }))
  act(() => result.current.dispatch({ type: 'ADD_TO_GARAGE', payload: car }))
  expect(result.current.state.garage).toHaveLength(1)
})

it('REMOVE_FROM_GARAGE removes by id', () => {
  const { result } = renderHook(() => useApp(), { wrapper })
  act(() => result.current.dispatch({ type: 'ADD_TO_GARAGE', payload: car }))
  act(() => result.current.dispatch({ type: 'REMOVE_FROM_GARAGE', payload: car.id }))
  expect(result.current.state.garage).toHaveLength(0)
})
