export interface DropdownOption {
  id: number
  name: string
}

export interface ActiveCar {
  id: number
  year: string
  make: string
  model: string
  trim: string
  engine: string
}

export interface GarageItem extends ActiveCar {}

export interface PartImage {
  part_id: number
  image_id: number
  part_image_text: string
  image: {
    id: number
    name: string
    bucket_path: string
    url: string | null
    alt_text: string
  }
}

export interface Part {
  id: number
  part_number: string
  title: string
  description: string
  category_id: number
  positions: string | null
  notes: string | null
  replaces: string | null
  other_names: string | null
  images: PartImage[]
}

export interface CompatibleCar {
  id: number
  year: { id: number; name: string }
  make: { id: number; name: string }
  model: { id: number; name: string }
  trim: { id: number; name: string }
  engine: { id: number; name: string }
}

export interface ApiPage<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
  has_next: boolean
  has_prev: boolean
}
