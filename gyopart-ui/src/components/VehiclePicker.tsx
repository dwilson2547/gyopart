import { useState } from 'react'
import { useVehicleTree } from '../hooks/useVehicleTree'
import { useApp } from '../context/AppContext'
import { api } from '../api'
import type { Engine, Make, Trim, VehicleModel, Year } from '../types'

const SELECT_CLS = 'w-full bg-slate-800 border border-slate-700 text-white rounded px-2 py-2 text-sm disabled:opacity-40'

export function VehiclePicker() {
  const tree = useVehicleTree()
  const { dispatch } = useApp()
  const [configError, setConfigError] = useState<string | null>(null)

  async function handleSetActive() {
    const { year, make, model, trim, engine } = tree.sel
    if (!year || !make || !model || !trim || !engine) return
    setConfigError(null)
    const cars = await api.cars(year.id, make.id, model.id, trim.id, engine.id)
    if (!cars.length) {
      setConfigError('No matching vehicle configuration found. Try a different combination.')
      return
    }
    dispatch({
      type: 'SET_VEHICLE',
      payload: {
        car: cars[0],
        yearName: year.name,
        makeName: make.name,
        modelName: model.name,
        trimName: trim.name,
        engineName: engine.name,
      },
    })
  }

  const resolved = !!(tree.sel.year && tree.sel.make && tree.sel.model && tree.sel.trim && tree.sel.engine)

  return (
    <div className="flex flex-col gap-3 p-4">
      {(tree.error || configError) && (
        <p className="text-xs text-red-400">{configError ?? tree.error}</p>
      )}

      <select
        aria-label="Year"
        className={SELECT_CLS}
        value={tree.sel.year?.id ?? ''}
        onChange={e => {
          const y = tree.years.find((y: Year) => y.id === Number(e.target.value))
          if (y) tree.selectYear(y)
        }}
      >
        <option value="" disabled>Year</option>
        {tree.years.map((y: Year) => <option key={y.id} value={y.id}>{y.name}</option>)}
      </select>

      <select
        key={tree.sel.year?.id ?? 'make'}
        aria-label="Make"
        className={SELECT_CLS}
        disabled={!tree.sel.year || tree.loadingField === 'makes'}
        value={tree.sel.make?.id ?? ''}
        onChange={e => {
          const m = tree.makes.find((m: Make) => m.id === Number(e.target.value))
          if (m) tree.selectMake(m)
        }}
      >
        {tree.loadingField === 'makes'
          ? <option>Loading…</option>
          : <>
              <option value="" disabled>Make</option>
              {tree.makes.map((m: Make) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </>
        }
      </select>

      <select
        key={tree.sel.make?.id ?? 'model'}
        aria-label="Model"
        className={SELECT_CLS}
        disabled={!tree.sel.make || tree.loadingField === 'models'}
        value={tree.sel.model?.id ?? ''}
        onChange={e => {
          const m = tree.models.find((m: VehicleModel) => m.id === Number(e.target.value))
          if (m) tree.selectModel(m)
        }}
      >
        {tree.loadingField === 'models'
          ? <option>Loading…</option>
          : <>
              <option value="" disabled>Model</option>
              {tree.models.map((m: VehicleModel) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </>
        }
      </select>

      <select
        key={tree.sel.model?.id ?? 'trim'}
        aria-label="Trim"
        className={SELECT_CLS}
        disabled={!tree.sel.model || tree.loadingField === 'trims'}
        value={tree.sel.trim?.id ?? ''}
        onChange={e => {
          const t = tree.trims.find((t: Trim) => t.id === Number(e.target.value))
          if (t) tree.selectTrim(t)
        }}
      >
        {tree.loadingField === 'trims'
          ? <option>Loading…</option>
          : <>
              <option value="" disabled>Trim</option>
              {tree.trims.map((t: Trim) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </>
        }
      </select>

      <select
        key={tree.sel.trim?.id ?? 'engine'}
        aria-label="Engine"
        className={SELECT_CLS}
        disabled={!tree.sel.trim || tree.loadingField === 'engines'}
        value={tree.sel.engine?.id ?? ''}
        onChange={e => {
          const eng = tree.engines.find((eng: Engine) => eng.id === Number(e.target.value))
          if (eng) tree.selectEngine(eng)
        }}
      >
        {tree.loadingField === 'engines'
          ? <option>Loading…</option>
          : <>
              <option value="" disabled>Engine</option>
              {tree.engines.map((eng: Engine) => <option key={eng.id} value={eng.id}>{eng.name}</option>)}
            </>
        }
      </select>

      <button
        disabled={!resolved}
        onClick={handleSetActive}
        className="w-full bg-amber-500 text-black font-semibold py-2 rounded text-sm disabled:opacity-40 hover:bg-amber-400 transition-colors"
      >
        Set Active Vehicle
      </button>
    </div>
  )
}
