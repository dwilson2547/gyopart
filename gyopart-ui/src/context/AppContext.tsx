import { createContext, useContext, useReducer, type Dispatch, type ReactNode } from 'react'
import type { Part, SelectedVehicle, YardResult } from '../types'

interface AppState {
  selectedVehicle: SelectedVehicle | null
  activePart: Part | null
  zip: string
  radiusMiles: number
  results: YardResult[]
  searching: boolean
}

type Action =
  | { type: 'SET_VEHICLE'; payload: SelectedVehicle }
  | { type: 'CLEAR_VEHICLE' }
  | { type: 'SET_PART'; payload: Part }
  | { type: 'CLEAR_PART' }
  | { type: 'SET_ZIP'; payload: string }
  | { type: 'SET_RADIUS'; payload: number }
  | { type: 'SET_RESULTS'; payload: YardResult[] }
  | { type: 'SET_SEARCHING'; payload: boolean }

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_VEHICLE':
      return { ...state, selectedVehicle: action.payload, activePart: null, results: [] }
    case 'CLEAR_VEHICLE':
      return { ...state, selectedVehicle: null, activePart: null, results: [] }
    case 'SET_PART':
      return { ...state, activePart: action.payload, results: [] }
    case 'CLEAR_PART':
      return { ...state, activePart: null, results: [] }
    case 'SET_ZIP':
      return { ...state, zip: action.payload }
    case 'SET_RADIUS':
      return { ...state, radiusMiles: action.payload }
    case 'SET_RESULTS':
      return { ...state, results: action.payload }
    case 'SET_SEARCHING':
      return { ...state, searching: action.payload }
  }
}

const initial: AppState = {
  selectedVehicle: null,
  activePart: null,
  zip: '',
  radiusMiles: 50,
  results: [],
  searching: false,
}

const AppContext = createContext<{ state: AppState; dispatch: Dispatch<Action> } | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial)
  return <AppContext.Provider value={{ state, dispatch }}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
