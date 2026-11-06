export type FieldType =
  | 'text'
  | 'select'
  | 'radio'
  | 'number'
  | 'currency'
  | 'checklist'
  | 'multiselect'
  | 'records'
  | 'incentives'

export type ShowIf = { field: string; equals: string }

export type Field = {
  id: string
  label: string
  type: FieldType
  required: boolean
  options?: string[]
  help?: string
  placeholder?: string
  placement?: 'top' | 'map' // 'top': the box beside the map; 'map': under the map
  format?: 'postal_code'
  show_if?: ShowIf
  unit_kind?: 'area' | 'temperature' | 'power' | 'length'
  integer?: boolean
  min?: number
  max?: number
  other_text?: boolean
  max_records?: number
  year_range?: [number, number]
  ranges?: { label: string; min: number | null; max: number | null }[] // e.g. which generation a year falls in
  numeric?: Record<string, number> // a dropdown option that stands for a number (storeys, floor area band)
  labels_by_unit?: Record<string, string[]> // how each option reads in another unit system, same order as options
  type_options?: string[] // renovation records: the building elements to choose from
  must_match_postal?: { field: string; zones_by_letter: Record<string, string[]> } // zone ids that fit each postal code letter
  not_more_than?: { field: string; message: string } // e.g. storeys above ground <= total storeys
}

export type Section = { id: string; title: string; fields: Field[] }

export type UnitSystem = { area: string; temperature: string; length: string }

export type Spec = {
  unit_field: string
  unit_systems: Record<string, UnitSystem>
  sections: Section[]
}

export type Renovation = { type: string; year: string }
export type Answer = string | string[] | Renovation[]
export type Answers = Record<string, Answer>

export type Incentive = {
  id: string
  name: string
  eligibility: string
  amount: string
  deadline: string
  last_verified: string | null
}

export type ApiError = { field: string; message: string }
