import { Navigate, Route, Routes } from 'react-router'
import { Shell } from './components/Shell'
import { VehicleChooser } from './components/VehiclePicker'
import { CarPage } from './pages/CarPage'
import { GaragePage } from './pages/GaragePage'
import { InterchangePage } from './pages/InterchangePage'
import { PartPage } from './pages/PartPage'
import { PartYardsPage } from './pages/PartYardsPage'
import { YardPage } from './pages/YardPage'
import { YardsPage } from './pages/YardsPage'
import { useGarage } from './state/garageContext'

function Home() {
  const { active } = useGarage()
  if (active) return <Navigate to={`/car/${active.car_id}`} replace />
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-4 py-6">
      <div>
        <h1 className="text-xl font-semibold">Choose a vehicle</h1>
        <p className="text-sm text-muted">Pick a car to browse its parts catalogue.</p>
      </div>
      <section className="rounded-xl border border-line bg-surface p-4 sm:p-5"><VehicleChooser /></section>
    </div>
  )
}

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/garage" element={<GaragePage />} />
        <Route path="/car/:carId" element={<CarPage />} />
        <Route path="/part/:partId" element={<PartPage />} />
        <Route path="/part/:partId/interchange" element={<InterchangePage />} />
        <Route path="/part/:partId/yards" element={<PartYardsPage />} />
        <Route path="/yards" element={<YardsPage />} />
        <Route path="/yards/:yardId" element={<YardPage />} />
        <Route path="*" element={<div className="p-6 text-muted">Page not found.</div>} />
      </Routes>
    </Shell>
  )
}
