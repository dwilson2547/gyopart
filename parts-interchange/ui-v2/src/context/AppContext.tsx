import { createContext, useContext, useReducer, type ReactNode } from 'react'
import type { ActiveCar, GarageItem, Part } from '../types'
import { loadGarage, saveGarage } from '../lib/garage'

interface AppState {
  activeCar: ActiveCar | null
  activePart: Part | null
  garage: GarageItem[]
}

type Action =
  | { type: 'SET_ACTIVE_CAR'; payload: ActiveCar }
  | { type: 'SET_ACTIVE_PART'; payload: Part }
  | { type: 'ADD_TO_GARAGE'; payload: GarageItem }
  | { type: 'REMOVE_FROM_GARAGE'; payload: number }

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_ACTIVE_CAR':
      return { ...state, activeCar: action.payload, activePart: null }
    case 'SET_ACTIVE_PART':
      return { ...state, activePart: action.payload }
    case 'ADD_TO_GARAGE': {
      if (state.garage.find(g => g.id === action.payload.id)) return state
      const next = [...state.garage, action.payload]
      saveGarage(next)
      return { ...state, garage: next }
    }
    case 'REMOVE_FROM_GARAGE': {
      const next = state.garage.filter(g => g.id !== action.payload)
      saveGarage(next)
      return { ...state, garage: next }
    }
    default:
      return state
  }
}

const AppContext = createContext<{ state: AppState; dispatch: React.Dispatch<Action> } | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, {
    activeCar: null,
    activePart: null,
    garage: loadGarage(),
  })
  return <AppContext.Provider value={{ state, dispatch }}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
