export type FieldType = 'text' | 'select' | 'number' | 'currency' | 'weights'

export type ShowIf = { field: string; equals: string }

export type Criterion = { id: string; label: string; default: number }

export type Field = {
  id: string
  label: string
  type: FieldType
  required: boolean
  options?: string[]
  help?: string
  placeholder?: string
  placement?: 'map' // shown under the map instead of with the other questions
  format?: 'postal_code'
  show_if?: ShowIf
  integer?: boolean
  min?: number
  max?: number
  criteria?: Criterion[] // weights: the criteria with a slider each
  must_match_postal?: { field: string; zones_by_letter: Record<string, string[]> } // zone ids that fit each postal code letter
}

export type Section = { id: string; title: string; fields: Field[] }

export type Spec = { sections: Section[] }

export type Weights = Record<string, number>
export type Answer = string | Weights
export type Answers = Record<string, Answer>

export type ApiError = { field: string; message: string }

export type Package = {
  id: string
  name: string
  tag: string
  description: string
  cost: number
  incentive: number
  net_cost: number
  saving_pct: number
  carbon_t: number
  embodied_t: number
  payback_yrs: number
  resilience: number
  score: number
  within_budget: boolean
}

export type Report = {
  archetype: { id: string; building_form: string; period: string; confidence: number }
  baseline: { energy_kwh: number; heating_kwh: number; cooling_kwh: number; carbon_t: number }
  budget: number
  weights: Record<string, number>
  packages: Package[] // best match for the user's priorities first
}

// How the recommendations step orders and filters the packages (on the page only, not sent).
export type SortMode = 'personal' | 'cost' | 'savings' | 'carbon' | 'payback'
export type BudgetFilter = 'within' | 'all'
