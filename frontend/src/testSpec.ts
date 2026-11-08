// A small questionnaire and report used only by the tests. It covers every kind of question the
// page can draw, so the tests do not depend on the real questions changing.
import type { Report, Spec } from './types'

export const ZONE_A = 'Zone 4: Mildest; mainly coastal southern BC (Vancouver, Victoria)'
export const ZONE_B = 'Zone 5: Southern BC/Alberta and southern Ontario/Quebec (Toronto, Windsor)'

export const SIMPLE = 'Simple – choose what matters most'
export const ADVANCED = 'Advanced – adjust numerical weights'

export const CRITERIA = [
  { id: 'initial_cost', label: 'Initial cost', default: 20 },
  { id: 'energy_savings', label: 'Energy savings', default: 25 },
  { id: 'payback', label: 'Payback', default: 15 },
]
export const DEFAULT_WEIGHTS = { initial_cost: 20, energy_savings: 25, payback: 15 }

export const TEST_SPEC: Spec = {
  sections: [
    {
      id: 'home',
      title: 'Tell us about your home',
      fields: [
        { id: 'postal_code', label: 'Postal code / location', type: 'text', required: true, format: 'postal_code' },
        { id: 'year_built', label: 'Approximate construction year', type: 'number', required: true, integer: true, min: 1800, max: 2026 },
        { id: 'floor_area', label: 'Approximate floor area (m²)', type: 'number', required: true, min: 30, max: 1000 },
        { id: 'building_form', label: 'Building form (if known)', type: 'select', required: false, options: ['Detached house', 'Townhouse', 'Not sure'] },
        { id: 'zone', label: 'Climate zone', type: 'select', required: true, options: [ZONE_A, ZONE_B], placement: 'map', must_match_postal: { field: 'postal_code', zones_by_letter: { V: ['zone4', 'zone5'], N: ['zone5'] } } },
      ],
    },
    {
      id: 'priorities',
      title: 'Set your budget and priorities',
      fields: [
        { id: 'budget', label: 'Available retrofit budget (CAD)', type: 'currency', required: true, min: 0, max: 10000000 },
        { id: 'preference_mode', label: 'Preference setting', type: 'select', required: true, options: [SIMPLE, ADVANCED] },
        { id: 'priority', label: 'What matters most to you?', type: 'select', required: true, options: ['Balanced outcome', 'Lowest upfront cost'], show_if: { field: 'preference_mode', equals: SIMPLE } },
        { id: 'secondary_priority', label: 'Second priority', type: 'select', required: false, options: ['Energy savings', 'Short payback'], show_if: { field: 'preference_mode', equals: SIMPLE } },
        { id: 'weights', label: 'Criteria weights', type: 'weights', required: true, min: 0, max: 100, criteria: CRITERIA, show_if: { field: 'preference_mode', equals: ADVANCED } },
      ],
    },
  ],
}

const pkg = (id: string, name: string, cost: number, saving: number, payback: number, score: number, within: boolean) => ({
  id,
  name,
  tag: `${name} tag`,
  description: `${name} description`,
  cost,
  incentive: Math.round(cost / 10),
  net_cost: cost - Math.round(cost / 10),
  saving_pct: saving,
  carbon_t: saving / 20,
  embodied_t: saving / 10,
  payback_yrs: payback,
  resilience: 50 + saving,
  score,
  within_budget: within,
})

export const TEST_REPORT: Report = {
  archetype: { id: 'detached_gen1', building_form: 'Detached house', period: 'Generation 1 (1941 - 1996)', confidence: 1 },
  baseline: { energy_kwh: 28800, heating_kwh: 20160, cooling_kwh: 2880, carbon_t: 5.8 },
  budget: 30000,
  weights: { initial_cost: 0.3, energy_savings: 0.45, payback: 0.25 },
  packages: [
    pkg('combined', 'Whole-home package', 39000, 58, 11.6, 0.6, false),
    pkg('heatpump', 'Heat pump package', 18500, 31, 9.1, 0.55, true),
    pkg('basic', 'Air sealing package', 11500, 22, 7.4, 0.5, true),
  ],
}
