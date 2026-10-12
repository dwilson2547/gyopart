import { Navigate, Route, Routes } from 'react-router'
import { Shell } from './components/Shell'
import { CarPage } from './pages/CarPage'
import { GaragePage } from './pages/GaragePage'
import { PartPage } from './pages/PartPage'
import { useGarage } from './state/garageContext'

function Home() {
  const { active } = useGarage()
  return <Navigate to={active ? `/car/${active.car_id}` : '/garage'} replace />
}

export default function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/garage" element={<GaragePage />} />
        <Route path="/car/:carId" element={<CarPage />} />
        <Route path="/part/:partId" element={<PartPage />} />
        <Route path="/part/:partId/interchange" element={<div className="p-6 text-muted">Interchange — coming next.</div>} />
        <Route path="/part/:partId/yards" element={<div className="p-6 text-muted">Yards — coming soon.</div>} />
        <Route path="*" element={<div className="p-6 text-muted">Page not found.</div>} />
      </Routes>
    </Shell>
  )
}
