import { MapPin, Phone } from 'lucide-react'
import type { YardResult } from '../types'

export function YardCard({ yard }: { yard: YardResult }) {
  return (
    <div className="bg-slate-800 rounded-lg p-4 mb-3 border border-slate-700">
      <div className="flex justify-between items-start mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-white font-semibold text-sm">{yard.name}</h3>
          {yard.address && (
            <p className="flex items-center gap-1 text-slate-400 text-xs mt-0.5">
              <MapPin size={10} />
              {yard.address}, {yard.city}, {yard.state} {yard.zip_code}
            </p>
          )}
          {yard.phone && (
            <p className="flex items-center gap-1 text-slate-500 text-xs mt-0.5">
              <Phone size={10} />
              {yard.phone}
            </p>
          )}
        </div>
        <div className="text-right ml-4 flex-shrink-0">
          <span className="text-amber-400 font-bold text-lg">{yard.distance_miles.toFixed(1)}</span>
          <span className="text-amber-400 text-xs"> mi</span>
          <p className="text-slate-400 text-xs mt-0.5">
            {yard.matching_vehicles.length} vehicle{yard.matching_vehicles.length !== 1 ? 's' : ''}
          </p>
        </div>
      </div>

      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500 border-b border-slate-700">
            <th className="text-left py-1 font-medium">Year</th>
            <th className="text-left py-1 font-medium">Make</th>
            <th className="text-left py-1 font-medium">Model</th>
            <th className="text-left py-1 font-medium">Trim</th>
            <th className="text-left py-1 font-medium">Row</th>
          </tr>
        </thead>
        <tbody>
          {yard.matching_vehicles.map(v => (
            <tr key={v.vehicle_id} className="text-slate-300 border-b border-slate-700/40 last:border-0">
              <td className="py-1">{v.year ?? '—'}</td>
              <td className="py-1">{v.make ?? '—'}</td>
              <td className="py-1">{v.model ?? '—'}</td>
              <td className="py-1">{v.trim ?? '—'}</td>
              <td className="py-1 font-mono">{v.row ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
