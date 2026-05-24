import { useState } from 'react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { useVehicleTree } from '../hooks/useVehicleTree'
import { useApp } from '../context/AppContext'

export function VehiclePicker() {
  const { state, dispatch } = useApp()
  const tree = useVehicleTree()
  const [collapsed, setCollapsed] = useState(false)

  if (collapsed && state.activeCar) {
    const { year, make, model, trim, engine } = state.activeCar
    return (
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-sm text-zinc-400">{year} {make} {model} · {trim} · {engine}</span>
        <button onClick={() => setCollapsed(false)} className="text-xs text-amber-500 hover:underline">Change</button>
      </div>
    )
  }

  const resolved = tree.sel.year && tree.sel.make && tree.sel.model && tree.sel.trim && tree.sel.engine

  async function handleSetActive() {
    if (!tree.sel.engine) return
    const car = await tree.selectEngine(tree.sel.engine.id, tree.sel.engine.label)
    if (car) {
      dispatch({ type: 'SET_ACTIVE_CAR', payload: car })
      setCollapsed(true)
    }
  }

  function handleAddToGarage() {
    if (!state.activeCar) return
    dispatch({ type: 'ADD_TO_GARAGE', payload: state.activeCar })
  }

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      {tree.error && <p className="text-xs text-red-400">{tree.error} — <button onClick={() => window.location.reload()} className="underline">retry</button></p>}

      <Select onValueChange={v => { const opt = tree.years.find(y => y.id === Number(v)); if (opt) tree.selectYear(opt.id, opt.name) }}>
        <SelectTrigger className="bg-slate-800 border-slate-700"><SelectValue placeholder="Year" /></SelectTrigger>
        <SelectContent>{tree.years.map(y => <SelectItem key={y.id} value={String(y.id)}>{y.name}</SelectItem>)}</SelectContent>
      </Select>

      <Select disabled={!tree.sel.year} onValueChange={v => { const opt = tree.makes.find(m => m.id === Number(v)); if (opt) tree.selectMake(opt.id, opt.name) }}>
        <SelectTrigger className="bg-slate-800 border-slate-700"><SelectValue placeholder="Make" /></SelectTrigger>
        <SelectContent>{tree.makes.map(m => <SelectItem key={m.id} value={String(m.id)}>{m.name}</SelectItem>)}</SelectContent>
      </Select>

      <Select disabled={!tree.sel.make} onValueChange={v => { const opt = tree.models.find(m => m.id === Number(v)); if (opt) tree.selectModel(opt.id, opt.name) }}>
        <SelectTrigger className="bg-slate-800 border-slate-700"><SelectValue placeholder="Model" /></SelectTrigger>
        <SelectContent>{tree.models.map(m => <SelectItem key={m.id} value={String(m.id)}>{m.name}</SelectItem>)}</SelectContent>
      </Select>

      <Select disabled={!tree.sel.model} onValueChange={v => { const opt = tree.trims.find(t => t.id === Number(v)); if (opt) tree.selectTrim(opt.id, opt.name) }}>
        <SelectTrigger className="bg-slate-800 border-slate-700"><SelectValue placeholder="Trim" /></SelectTrigger>
        <SelectContent>{tree.trims.map(t => <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>)}</SelectContent>
      </Select>

      <Select disabled={!tree.sel.trim} onValueChange={v => { const opt = tree.engines.find(e => e.id === Number(v)); if (opt) tree.pickEngine(opt.id, opt.name) }}>
        <SelectTrigger className="bg-slate-800 border-slate-700"><SelectValue placeholder="Engine" /></SelectTrigger>
        <SelectContent>{tree.engines.map(e => <SelectItem key={e.id} value={String(e.id)}>{e.name}</SelectItem>)}</SelectContent>
      </Select>

      <div className="flex gap-2 pt-1">
        <Button disabled={!resolved} onClick={handleSetActive} className="flex-1 bg-amber-500 text-black hover:bg-amber-400 text-sm">
          Set Active
        </Button>
        <Button disabled={!state.activeCar} variant="outline" onClick={handleAddToGarage} className="flex-1 border-slate-700 text-sm">
          Add to Garage
        </Button>
      </div>
    </div>
  )
}
