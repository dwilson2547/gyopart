import { useState, useEffect } from 'react'
import { api } from '../api'
import type { Engine, Make, Trim, VehicleModel, Year } from '../types'

interface Sel {
  year: Year | null
  make: Make | null
  model: VehicleModel | null
  trim: Trim | null
  engine: Engine | null
}

export function useVehicleTree() {
  const [years, setYears] = useState<Year[]>([])
  const [makes, setMakes] = useState<Make[]>([])
  const [models, setModels] = useState<VehicleModel[]>([])
  const [trims, setTrims] = useState<Trim[]>([])
  const [engines, setEngines] = useState<Engine[]>([])
  const [sel, setSel] = useState<Sel>({ year: null, make: null, model: null, trim: null, engine: null })
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.years().then(setYears).catch(() => setError('Failed to load years'))
  }, [])

  function selectYear(year: Year) {
    setSel({ year, make: null, model: null, trim: null, engine: null })
    setMakes([]); setModels([]); setTrims([]); setEngines([])
    api.makes(year.id).then(setMakes).catch(() => setError('Failed to load makes'))
  }

  function selectMake(make: Make) {
    if (!sel.year) return
    setSel({ ...sel, make, model: null, trim: null, engine: null })
    setModels([]); setTrims([]); setEngines([])
    api.models(sel.year.id, make.id).then(setModels).catch(() => setError('Failed to load models'))
  }

  function selectModel(model: VehicleModel) {
    if (!sel.year || !sel.make) return
    setSel({ ...sel, model, trim: null, engine: null })
    setTrims([]); setEngines([])
    api.trims(sel.year.id, sel.make.id, model.id).then(setTrims).catch(() => setError('Failed to load trims'))
  }

  function selectTrim(trim: Trim) {
    if (!sel.year || !sel.make || !sel.model) return
    setSel({ ...sel, trim, engine: null })
    setEngines([])
    api.engines(sel.year.id, sel.make.id, sel.model.id, trim.id)
      .then(setEngines).catch(() => setError('Failed to load engines'))
  }

  function selectEngine(engine: Engine) {
    setSel(s => ({ ...s, engine }))
  }

  return { years, makes, models, trims, engines, sel, error, selectYear, selectMake, selectModel, selectTrim, selectEngine }
}
