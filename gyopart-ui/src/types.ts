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
