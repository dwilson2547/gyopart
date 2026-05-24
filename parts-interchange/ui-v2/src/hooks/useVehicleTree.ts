import { useState, useEffect } from 'react'
import * as api from '../lib/api'
import type { DropdownOption } from '../types'

interface Selection { id: number; label: string }

interface Selections {
  year: Selection | null
  make: Selection | null
  model: Selection | null
  trim: Selection | null
  engine: Selection | null
}

export function useVehicleTree() {
  const [years, setYears] = useState<DropdownOption[]>([])
  const [makes, setMakes] = useState<DropdownOption[]>([])
  const [models, setModels] = useState<DropdownOption[]>([])
  const [trims, setTrims] = useState<DropdownOption[]>([])
  const [engines, setEngines] = useState<DropdownOption[]>([])
  const [sel, setSel] = useState<Selections>({ year: null, make: null, model: null, trim: null, engine: null })
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getYears().then(setYears).catch(() => setError('Failed to load years'))
  }, [])

  // Cascade: load makes when year changes
  useEffect(() => {
    if (!sel.year) { setMakes([]); return }
    api.getMakes(sel.year.id).then(setMakes).catch(() => setError('Failed to load makes'))
  }, [sel.year])

  // Cascade: load models when make changes
  useEffect(() => {
    if (!sel.year || !sel.make) { setModels([]); return }
    api.getModels(sel.year.id, sel.make.id).then(setModels).catch(() => setError('Failed to load models'))
  // sel.year is stable at this point; only re-run when make changes
  }, [sel.make]) // eslint-disable-line react-hooks/exhaustive-deps

  // Cascade: load trims when model changes
  useEffect(() => {
    if (!sel.year || !sel.make || !sel.model) { setTrims([]); return }
    api.getTrims(sel.year.id, sel.make.id, sel.model.id).then(setTrims).catch(() => setError('Failed to load trims'))
  // sel.year and sel.make are stable at this point; only re-run when model changes
  }, [sel.model]) // eslint-disable-line react-hooks/exhaustive-deps

  // Cascade: load engines when trim changes
  useEffect(() => {
    if (!sel.year || !sel.make || !sel.model || !sel.trim) { setEngines([]); return }
    api.getEngines(sel.year.id, sel.make.id, sel.model.id, sel.trim.id).then(setEngines).catch(() => setError('Failed to load engines'))
  // sel.year/make/model are stable at this point; only re-run when trim changes
  }, [sel.trim]) // eslint-disable-line react-hooks/exhaustive-deps

  function selectYear(id: number, label: string) {
    setSel({ year: { id, label }, make: null, model: null, trim: null, engine: null })
    setModels([])
    setTrims([])
    setEngines([])
  }

  function selectMake(id: number, label: string) {
    setSel(s => ({ ...s, make: { id, label }, model: null, trim: null, engine: null }))
    setTrims([])
    setEngines([])
  }

  function selectModel(id: number, label: string) {
    setSel(s => ({ ...s, model: { id, label }, trim: null, engine: null }))
    setEngines([])
  }

  function selectTrim(id: number, label: string) {
    setSel(s => ({ ...s, trim: { id, label }, engine: null }))
  }

  function pickEngine(id: number, label: string) {
    setSel(s => ({ ...s, engine: { id, label } }))
  }

  async function selectEngine(id: number, label: string) {
    if (!sel.year || !sel.make || !sel.model || !sel.trim) return
    setSel(s => ({ ...s, engine: { id, label } }))
    try {
      const cars = await api.getCars(sel.year.id, sel.make.id, sel.model.id, sel.trim.id, id)
      if (!cars.length) { setError('No matching vehicle found'); return }
      return { id: cars[0].id, year: sel.year.label, make: sel.make.label, model: sel.model.label, trim: sel.trim.label, engine: label }
    } catch { setError('Failed to resolve vehicle') }
  }

  return { years, makes, models, trims, engines, sel, error, selectYear, selectMake, selectModel, selectTrim, pickEngine, selectEngine }
}
