export interface Year { id: number; name: string }
export interface Make { id: number; name: string }
export interface VehicleModel { id: number; name: string; make_id: number }
export interface Trim { id: number; name: string }
export interface Engine { id: number; name: string }
export interface Car {
  id: number
  year_id: number; make_id: number; model_id: number; trim_id: number; engine_id: number
}
export interface Part {
  id: number
  title: string | null
  part_number: string | null
  description: string | null
  other_names: string | null
}
export interface PagedPartsResponse {
  items: Part[]
  total: number
  page: number
  per_page: number
}
export interface VehicleResult {
  vehicle_id: number
  year: number | null
  make: string | null
  model: string | null
  trim: string | null
  row: string | null
  car_id: number | null
}
export interface YardResult {
  location_id: number
  name: string
  address: string | null
  city: string | null
  state: string | null
  zip_code: string | null
  phone: string | null
  distance_miles: number
  matching_vehicles: VehicleResult[]
}
export interface SearchResponse { results: YardResult[] }

export interface SelectedVehicle {
  car: Car
  yearName: string; makeName: string; modelName: string; trimName: string; engineName: string
}

export interface Category { id: number; name: string }
export interface Diagram { id: number; category_id: number; sub_category_id: number; image_id: number }
export interface DiagramPart extends Part { part_index: string }
export interface DiagramDetail {
  id: number
  category_id: number
  sub_category_id: number
  image_url: string
  image_alt: string
  parts: DiagramPart[]
}
