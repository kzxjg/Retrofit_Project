// A small questionnaire used only by the tests. It covers every kind of question the page
// can draw, so the tests do not depend on the real questions changing.
import type { Incentive, Spec } from './types'

export const ZONE_A = 'Zone 4: Mildest; mainly coastal southern BC (Vancouver, Victoria)'
export const ZONE_B = 'Zone 8: Far northern Canada (Yellowknife, Iqaluit)'

export const YEAR_RANGES = [
  { label: 'Pre 1941', min: null, max: 1940 },
  { label: 'Generation 1 (1941 - 1996)', min: 1941, max: 1996 },
  { label: 'Generation 2 (1997 - 2010)', min: 1997, max: 2010 },
  { label: 'Generation 3 (2011 - 2016)', min: 2011, max: 2016 },
  { label: 'Generation 4 (2017 - 2019)', min: 2017, max: 2019 },
  { label: 'Generation 5 (From 2020)', min: 2020, max: null },
]
export const TYPED_YEAR = '1985'
export const TYPED_YEAR_LABEL = 'Generation 1 (1941 - 1996)'

export const AREA_BANDS = ['Under 50 m²', '50–100 m²', '100–150 m²', '150–200 m²', '200–300 m²', '300–400 m²', 'Over 400 m²']
export const AREA_BANDS_FT = ['Under 540 ft²', '540–1,080 ft²', '1,080–1,610 ft²', '1,610–2,150 ft²', '2,150–3,230 ft²', '3,230–4,310 ft²', 'Over 4,310 ft²']
const AREA_NUMERIC = Object.fromEntries(AREA_BANDS.map((band, i) => [band, [40, 75, 125, 175, 250, 350, 500][i]]))
export const AREA = { A: AREA_BANDS[2], A_FT: AREA_BANDS_FT[2] } // the "100–150 m²" band, and how it reads in ft²
export const STOREYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']
const STOREY_NUMBERS = Object.fromEntries(STOREYS.map((s) => [s, Number(s)]))
export const RENOVATION_ELEMENTS = ['Walls', 'Roof', 'HVAC system', 'Windows', 'Doors']

export const METRIC = 'Metric (m², kWh)'
export const IMPERIAL = 'Imperial (ft², Btu)'

export const TEST_SPEC: Spec = {
  unit_field: 'preferred_units',
  unit_systems: {
    [METRIC]: { area: 'm²', temperature: '°C', length: 'mm' },
    [IMPERIAL]: { area: 'ft²', temperature: '°F', length: 'in' },
  },
  sections: [
    {
      id: 'general',
      title: 'General building information',
      fields: [
        { id: 'postal_code', label: "What is the building's postal code?", type: 'text', required: true, format: 'postal_code', placement: 'top' },
        { id: 'year_built', label: 'Year built', type: 'number', required: true, integer: true, min: 1800, max: 2026, placement: 'top', ranges: YEAR_RANGES },
        { id: 'zone', label: 'Climate zone', type: 'select', required: true, options: [ZONE_A, ZONE_B], placement: 'map', must_match_postal: { field: 'postal_code', zones_by_letter: { V: ['zone4'], Y: ['zone8'] } } },
        { id: 'preferred_units', label: 'Preferred units', type: 'radio', required: true, options: [METRIC, IMPERIAL], placement: 'top' },
        { id: 'floor_area', label: 'Total floor area', type: 'select', required: true, placement: 'top', options: AREA_BANDS, numeric: AREA_NUMERIC, labels_by_unit: { [IMPERIAL]: AREA_BANDS_FT } },
        { id: 'storeys', label: 'Number of storeys', type: 'select', required: true, placement: 'top', options: STOREYS, numeric: STOREY_NUMBERS },
        { id: 'storeys_above_ground', label: 'Number of storeys above ground', type: 'select', required: false, placement: 'top', options: STOREYS, numeric: STOREY_NUMBERS, not_more_than: { field: 'storeys', message: 'Storeys above ground cannot be more than the total number of storeys.' } },
        { id: 'house_type', label: 'Type of house', type: 'select', required: true, options: ['Detached house', 'Row house or townhouse'], placement: 'top' },
        { id: 'renovation_history', label: 'Renovation history', type: 'records', required: false, max_records: 3, year_range: [2000, 2026], type_options: RENOVATION_ELEMENTS },
      ],
    },
    {
      id: 'energy',
      title: 'Energy consumption and indoor comfort',
      fields: [
        { id: 'energy_bill_winter', label: 'Typical monthly energy bill in winter', type: 'currency', required: false, min: 0, max: 20000 },
        { id: 'indoor_temperature', label: 'Preferred indoor temperature', type: 'number', required: false, unit_kind: 'temperature', min: 10, max: 30 },
        { id: 'household_equipment', label: 'Available household equipment', type: 'multiselect', required: false, options: ['Refrigerator', 'Freezer', 'Dishwasher'] },
      ],
    },
    {
      id: 'envelope',
      title: 'Building materials and envelope characteristics',
      fields: [
        { id: 'wall_materials', label: 'Exterior wall materials', type: 'multiselect', required: false, other_text: true, options: ['Brick', 'Vinyl siding', 'Other', 'Unknown'] },
        { id: 'wall_thickness', label: 'Exterior wall thickness', type: 'number', required: false, unit_kind: 'length', min: 20, max: 1500 },
      ],
    },
    {
      id: 'objectives',
      title: 'Retrofit objectives and constraints',
      fields: [
        { id: 'objectives', label: 'Main retrofit objective', type: 'checklist', required: true, options: ['Reduce energy bills', 'Improve thermal comfort'] },
        { id: 'target_subsidies', label: 'Expecting to target government subsidies', type: 'radio', required: false, options: ['Yes', 'No', 'Undecided'] },
        { id: 'subsidies', label: 'Government subsidies', type: 'incentives', required: false, show_if: { field: 'target_subsidies', equals: 'Yes' } },
      ],
    },
    {
      id: 'renewables',
      title: 'Renewable energy systems',
      fields: [
        { id: 'solar_existing', label: 'Existing solar PV installation', type: 'radio', required: false, options: ['Yes', 'No', 'Planned'] },
        { id: 'solar_capacity_kw', label: 'Existing solar PV capacity, if known', type: 'number', required: false, unit_kind: 'power', min: 0.1, max: 100, show_if: { field: 'solar_existing', equals: 'Yes' } },
      ],
    },
  ],
}

export const TEST_PROGRAMS: Incentive[] = [
  { id: 'a', name: 'Program A (test)', eligibility: 'Test eligibility', amount: 'Test amount', deadline: 'Test deadline', last_verified: null },
  { id: 'b', name: 'Program B (test)', eligibility: 'Other eligibility', amount: 'Other amount', deadline: 'Other deadline', last_verified: '2026-01-01' },
]
