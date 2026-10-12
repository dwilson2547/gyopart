import axios from 'axios'
import type { CarDetail, Named, VinDecode } from './types'

const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL ?? '' })

/** A readable message for an API failure: the API's `detail` when it sent one. */
export function errorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (err.response) return `Request failed (${err.response.status})`
    return 'Network error — is the API reachable?'
  }
  return String(err)
}

export const api = {
  years: () => http.get<Named[]>('/v1/vehicles/years').then(r => r.data),
  makes: (year_id: number) =>
    http.get<Named[]>('/v1/vehicles/makes', { params: { year_id } }).then(r => r.data),
  models: (year_id: number, make_id: number) =>
    http.get<Named[]>('/v1/vehicles/models', { params: { year_id, make_id } }).then(r => r.data),
  trims: (year_id: number, make_id: number, model_id: number) =>
    http.get<Named[]>('/v1/vehicles/trims', { params: { year_id, make_id, model_id } }).then(r => r.data),
  engines: (year_id: number, make_id: number, model_id: number, trim_id: number) =>
    http.get<Named[]>('/v1/vehicles/engines', { params: { year_id, make_id, model_id, trim_id } }).then(r => r.data),
  cars: (year_id: number, make_id: number, model_id: number, trim_id: number, engine_id: number) =>
    http.get<{ id: number }[]>('/v1/vehicles/cars', { params: { year_id, make_id, model_id, trim_id, engine_id } })
      .then(r => r.data),
  car: (car_id: number) => http.get<CarDetail>(`/v1/cars/${car_id}`).then(r => r.data),
  decodeVin: (vin: string) => http.get<VinDecode>(`/v1/vin/${encodeURIComponent(vin)}`).then(r => r.data),
}
