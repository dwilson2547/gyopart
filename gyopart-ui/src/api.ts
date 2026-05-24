import axios from 'axios'
import type {
  Car, Engine, Make, PagedPartsResponse, Part,
  SearchResponse, Trim, VehicleModel, Year,
} from './types'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8200',
})

export const api = {
  years: () =>
    http.get<Year[]>('/v1/vehicles/years').then(r => r.data),

  makes: (year_id: number) =>
    http.get<Make[]>('/v1/vehicles/makes', { params: { year_id } }).then(r => r.data),

  models: (year_id: number, make_id: number) =>
    http.get<VehicleModel[]>('/v1/vehicles/models', { params: { year_id, make_id } }).then(r => r.data),

  trims: (year_id: number, make_id: number, model_id: number) =>
    http.get<Trim[]>('/v1/vehicles/trims', { params: { year_id, make_id, model_id } }).then(r => r.data),

  engines: (year_id: number, make_id: number, model_id: number, trim_id: number) =>
    http.get<Engine[]>('/v1/vehicles/engines', { params: { year_id, make_id, model_id, trim_id } }).then(r => r.data),

  cars: (year_id: number, make_id: number, model_id: number, trim_id: number, engine_id: number) =>
    http.get<Car[]>('/v1/vehicles/cars', { params: { year_id, make_id, model_id, trim_id, engine_id } }).then(r => r.data),

  parts: (car_id: number, filter?: string, page = 1) =>
    http.get<PagedPartsResponse>('/v1/parts', { params: { car_id, filter, page } }).then(r => r.data),

  part: (part_id: number) =>
    http.get<Part>(`/v1/parts/${part_id}`).then(r => r.data),

  search: (part_id: number, zip: string, radius_miles = 50) =>
    http.get<SearchResponse>('/v1/search', { params: { part_id, zip, radius_miles } }).then(r => r.data),
}
