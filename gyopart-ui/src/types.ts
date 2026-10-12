export interface Named { id: number; name: string }

/** A catalogue car with its names (GET /v1/cars/{id}, VIN decode candidates). */
export interface CarDetail {
  car_id: number
  year_id: number; year: string
  make_id: number; make: string
  model_id: number; model: string
  trim_id: number | null; trim: string | null
  engine_id: number | null; engine: string | null
}

export interface VinDecoded {
  year: string | null
  make: string | null
  model: string | null
  trim: string | null
  series: string | null
  displacement_l: number | null
  cylinders: number | null
  fuel: string | null
  drive: string | null
  body: string | null
  error_code: string | null
  error_text: string | null
}

export interface VinDecode {
  vin: string
  decoded: VinDecoded
  candidates: CarDetail[]
  narrowed_by: string[]
}

/** A garage entry: the catalogue car plus the optional VIN and its decode. */
export interface GarageVehicle extends CarDetail {
  vin: string | null
  decoded: VinDecoded | null
  added_at: string
}

export interface TreeSubcategory { id: number; name: string; label: string; diagram_count: number }
export interface TreeCategory { id: number; name: string; label: string; subcategories: TreeSubcategory[] }

export interface CarDiagram {
  id: number
  category_id: number | null
  sub_category_id: number | null
  image_url: string | null
  label: string | null
  part_count: number
  fitting_part_count: number
}

export interface DiagramPart {
  part_index: string | null
  id: number
  title: string | null
  part_number: string | null
  description: string | null
  other_names: string | null
  fits: boolean | null
}

export interface DiagramDetail {
  id: number
  category_id: number | null
  sub_category_id: number | null
  image_url: string | null
  image_alt: string | null
  label: string | null
  parts: DiagramPart[]
}

export interface PartHit {
  part_id: number
  part_number: string | null
  title: string | null
  matched: 'title' | 'number' | 'other'
  diagram_id: number | null
  part_index: string | null
  category_id: number | null
  sub_category_id: number | null
}

export interface PartSearch { q: string; hits: PartHit[]; truncated: boolean }

export interface ImageSet { large: string; medium: string; small: string; callout: string | null }

export interface PartDiagram {
  diagram_id: number
  image_url: string | null
  label: string | null
  part_index: string | null
  category_id: number | null
  sub_category_id: number | null
}

export interface PartDetail {
  id: number
  part_number: string | null
  title: string | null
  other_names: string[]
  description: string | null
  replaces: string | null
  positions: string | null
  notes: string | null
  msrp: number | null
  manufacturer: string | null
  photos: ImageSet[]
  illustrations: ImageSet[]
  diagrams: PartDiagram[]
  fit_count: number
  fits_car: boolean | null
}

export interface PartSummary { id: number; title: string | null; part_number: string | null; description: string | null; other_names: string | null }

export interface InterchangeCar { car_id: number; trim: string | null; engine: string | null }
export interface InterchangeYear { year: number; cars: InterchangeCar[] }
export interface InterchangeModel { model: string; year_ranges: string; car_count: number; years: InterchangeYear[] }
export interface InterchangeMake { make: string; car_count: number; models: InterchangeModel[] }
export interface Interchange { part_id: number; car_count: number; makes: InterchangeMake[] }
