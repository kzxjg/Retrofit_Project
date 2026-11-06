import { describe, expect, it } from 'vitest'
import { allFields, buildPayload, displayValue, fieldIssue, isVisible, optionLabel, postalIssue, rangeLabel, sanitizeInput, unitSuffix, validate } from './formLogic'
import { AREA, IMPERIAL, METRIC, TEST_SPEC, TYPED_YEAR, TYPED_YEAR_LABEL, ZONE_A } from './testSpec'
import type { Answers } from './types'

const field = (id: string) => allFields(TEST_SPEC).find((f) => f.id === id)!

const COMPLETE: Answers = {
  postal_code: 'n9a 1a1',
  zone: ZONE_A,
  year_built: TYPED_YEAR,
  preferred_units: METRIC,
  floor_area: AREA.A,
  storeys: '2',
  house_type: 'Detached house',
  objectives: ['Reduce energy bills'],
}

describe('isVisible', () => {
  it('shows a conditional question only when its condition is met', () => {
    expect(isVisible(field('solar_capacity_kw'), {})).toBe(false)
    expect(isVisible(field('solar_capacity_kw'), { solar_existing: 'No' })).toBe(false)
    expect(isVisible(field('solar_capacity_kw'), { solar_existing: 'Yes' })).toBe(true)
    expect(isVisible(field('floor_area'), {})).toBe(true)
  })
})

describe('rangeLabel', () => {
  it('names the range a typed year falls in, including the ends', () => {
    const year = field('year_built')
    expect(rangeLabel(year, '1930')).toBe('Pre 1941')
    expect(rangeLabel(year, '1941')).toBe('Generation 1 (1941 - 1996)')
    expect(rangeLabel(year, '1996')).toBe('Generation 1 (1941 - 1996)')
    expect(rangeLabel(year, '1997')).toBe('Generation 2 (1997 - 2010)')
    expect(rangeLabel(year, ' 2024 ')).toBe('Generation 5 (From 2020)')
  })

  it('gives nothing for an empty, non-numeric or fractional entry, or a question without ranges', () => {
    const year = field('year_built')
    for (const bad of ['', '  ', 'abc', '1985.5', undefined]) expect(rangeLabel(year, bad)).toBeNull()
    expect(rangeLabel(field('floor_area'), '120')).toBeNull()
  })
})

describe('unitSuffix', () => {
  it('follows the chosen unit system, defaulting to the first one', () => {
    expect(unitSuffix(field('wall_thickness'), TEST_SPEC, {})).toBe('mm')
    expect(unitSuffix(field('wall_thickness'), TEST_SPEC, { preferred_units: IMPERIAL })).toBe('in')
    expect(unitSuffix(field('indoor_temperature'), TEST_SPEC, { preferred_units: IMPERIAL })).toBe('°F')
    expect(unitSuffix(field('energy_bill_winter'), TEST_SPEC, {})).toBe('CAD')
    expect(unitSuffix(field('solar_capacity_kw'), TEST_SPEC, {})).toBe('kW')
    expect(unitSuffix(field('house_type'), TEST_SPEC, {})).toBe('')
  })
})

describe('validate', () => {
  it('accepts a complete form', () => {
    expect(validate(TEST_SPEC, COMPLETE)).toEqual([])
  })

  it('asks for every required question that is empty', () => {
    const missing = validate(TEST_SPEC, {}).map((p) => p.field)
    for (const f of allFields(TEST_SPEC).filter((f) => f.required)) expect(missing).toContain(f.id)
    expect(missing).not.toContain('renovation_history')
  })

  it('does not ask for hidden questions', () => {
    const answers = { ...COMPLETE, solar_existing: 'No' }
    expect(validate(TEST_SPEC, answers)).toEqual([])
  })

  it('checks postal codes, numbers and whole numbers', () => {
    const bad = { ...COMPLETE, postal_code: '60601', energy_bill_winter: 'abc', year_built: '1985.5' }
    const fields = validate(TEST_SPEC, bad).map((p) => p.field)
    expect(fields).toEqual(expect.arrayContaining(['postal_code', 'energy_bill_winter', 'year_built']))
  })

  it('flags a half-filled renovation record', () => {
    const answers = { ...COMPLETE, renovation_history: [{ type: 'New roof', year: '' }] }
    expect(validate(TEST_SPEC, answers).map((p) => p.field)).toContain('renovation_history')
    const blank = { ...COMPLETE, renovation_history: [{ type: '', year: '' }] }
    expect(validate(TEST_SPEC, blank)).toEqual([])
  })
})

describe('buildPayload', () => {
  it('sends typed numbers as numbers, chosen options as they are, and tidies the postal code', () => {
    const payload = buildPayload(TEST_SPEC, { ...COMPLETE, energy_bill_winter: '250' })
    expect(payload.energy_bill_winter).toBe(250)
    expect(payload.year_built).toBe(1985)
    expect(payload.floor_area).toBe(AREA.A) // the server turns the chosen band into a number
    expect(payload.storeys).toBe('2')
    expect(payload.postal_code).toBe('N9A 1A1')
  })

  it('leaves out empty and hidden answers', () => {
    const payload = buildPayload(TEST_SPEC, { ...COMPLETE, solar_existing: 'No', solar_capacity_kw: '5', household_equipment: [] })
    expect(payload).not.toHaveProperty('solar_capacity_kw')
    expect(payload).not.toHaveProperty('household_equipment')
    expect(payload).not.toHaveProperty('energy_bill_winter')
  })

  it('sends complete renovation records and skips blank ones', () => {
    const payload = buildPayload(TEST_SPEC, {
      ...COMPLETE,
      renovation_history: [{ type: ' New roof ', year: '2015' }, { type: '', year: '' }],
    })
    expect(payload.renovation_history).toEqual([{ type: 'New roof', year: 2015 }])
  })

  it('sends the "other" text only when Other is ticked', () => {
    const withOther = buildPayload(TEST_SPEC, { ...COMPLETE, wall_materials: ['Brick', 'Other'], wall_materials_other: ' Stucco ' })
    expect(withOther.wall_materials_other).toBe('Stucco')
    const without = buildPayload(TEST_SPEC, { ...COMPLETE, wall_materials: ['Brick'], wall_materials_other: 'Stucco' })
    expect(without).not.toHaveProperty('wall_materials_other')
  })
})

describe('displayValue', () => {
  it('shows the range next to a typed year', () => {
    expect(displayValue(field('year_built'), TYPED_YEAR, TEST_SPEC, {})).toBe(`${TYPED_YEAR} (${TYPED_YEAR_LABEL})`)
  })

  it('adds units and formats lists, records and money', () => {
    expect(displayValue(field('wall_thickness'), '8', TEST_SPEC, { preferred_units: IMPERIAL })).toBe('8 in')
    expect(displayValue(field('wall_thickness'), '200', TEST_SPEC, {})).toBe('200 mm')
    expect(displayValue(field('energy_bill_winter'), '250', TEST_SPEC, {})).toBe('$250 CAD')
    expect(displayValue(field('objectives'), ['Reduce energy bills', 'Improve thermal comfort'], TEST_SPEC, {})).toBe(
      'Reduce energy bills, Improve thermal comfort',
    )
    expect(displayValue(field('renovation_history'), [{ type: 'Roof', year: '2015' }], TEST_SPEC, {})).toBe('Roof (2015)')
    expect(
      displayValue(field('wall_materials'), ['Brick', 'Other'], TEST_SPEC, { wall_materials_other: 'Stucco' }),
    ).toBe('Brick, Other: Stucco')
  })
})

describe('fieldIssue: what is wrong with an answer while it is being typed', () => {
  const issue = (id: string, value: string, answers: Answers = {}) => fieldIssue(field(id), value, TEST_SPEC, answers)

  it('says nothing about an empty answer, or one that is fine', () => {
    expect(issue('indoor_temperature', '')).toBeNull()
    expect(issue('indoor_temperature', '20')).toBeNull()
    expect(issue('indoor_temperature', '10')).toBeNull() // the limits themselves are allowed
    expect(issue('indoor_temperature', '30')).toBeNull()
  })

  it('shows a value that is too high at once, because typing more cannot fix it', () => {
    const found = issue('indoor_temperature', '45')!
    expect(found.message).toBe('Enter a value between 10 and 30 °C.')
    expect(found.early).toBe(true)
  })

  it('waits before calling a value too small, while more digits may still be coming', () => {
    expect(issue('indoor_temperature', '5')).toMatchObject({ early: false })
    expect(issue('year_built', '18')).toMatchObject({ early: false })
    // ...but not once it cannot grow: as long as the maximum, or negative
    expect(issue('year_built', '179')).toMatchObject({ early: false })
    expect(issue('year_built', '1799')).toMatchObject({ early: true }) // four digits already: it is too early a year
    expect(issue('energy_bill_winter', '-5')).toMatchObject({ early: true })
  })

  it('speaks the units the user chose and compares in those units', () => {
    const imperial: Answers = { preferred_units: IMPERIAL }
    expect(issue('indoor_temperature', '95', imperial)!.message).toBe('Enter a value between 50 and 86 °F.')
    expect(issue('indoor_temperature', '68', imperial)).toBeNull() // 20 °C
    expect(issue('indoor_temperature', '68')).toMatchObject({ early: true }) // 68 °C is far too hot
    // thickness: millimetres, or inches when the user chose imperial units
    expect(issue('wall_thickness', '200')).toBeNull()
    expect(issue('wall_thickness', '10')).not.toBeNull() // under 20 mm
    expect(issue('wall_thickness', '8', imperial)).toBeNull() // 203 mm
    expect(issue('wall_thickness', '0.5', imperial)!.message).toBe('Enter a value between 0.8 and 59 in.')
    expect(issue('wall_thickness', '60', imperial)).toMatchObject({ early: true }) // 1524 mm
  })

  it('writes money with a dollar sign and thousands separators', () => {
    expect(issue('energy_bill_winter', '25000')!.message).toBe('Enter an amount between $0 and $20,000 CAD.')
  })

  it('wants whole numbers where the question says so', () => {
    expect(issue('year_built', '1985.5')).toEqual({ message: 'Enter a whole number.', early: true })
    // a decimal point is refused even when the value looks whole
    for (const text of ['1985.0', '1985.00', '1985.5']) {
      expect(issue('year_built', text)?.message, text).toBe('Enter a whole number.')
    }

    expect(issue('year_built', '1985')).toBeNull()
    expect(issue('year_built', '1985.')).toBeNull() // a trailing dot is fine while typing
  })

  it('does not accept text where a number belongs', () => {
    expect(issue('energy_bill_winter', 'abc')).toEqual({ message: 'Enter a number.', early: true })
    expect(issue('energy_bill_winter', '-')).toEqual({ message: 'Enter a number.', early: false })
  })

  it('checks the year built against its own limits, without a unit', () => {
    expect(issue('year_built', '3000')!.message).toBe('Enter a whole number between 1800 and 2026.')
    expect(issue('year_built', '1985')).toBeNull()
  })

  it('keeps one answer within another when the question says so', () => {
    const rule = 'Storeys above ground cannot be more than the total number of storeys.'
    expect(issue('storeys_above_ground', '3', { storeys: '2' })).toEqual({ message: rule, early: false })
    expect(issue('storeys_above_ground', '2', { storeys: '2' })).toBeNull()
    expect(issue('storeys_above_ground', '3', {})).toBeNull() // nothing to compare with yet
    expect(issue('storeys_above_ground', '3', { storeys: '' })).toBeNull()
  })

  it('wants both halves of a renovation record', () => {
    const half = fieldIssue(field('renovation_history'), [{ type: 'New roof', year: '' }], TEST_SPEC, {})
    expect(half).toMatchObject({ early: false })
    expect(half!.message).toMatch(/Renovation 1/)
    expect(fieldIssue(field('renovation_history'), [{ type: '', year: '' }], TEST_SPEC, {})).toBeNull()
  })
})

describe('postalIssue: the Canada Post rules, character by character', () => {
  it('accepts a good code with or without the space, in any case', () => {
    for (const ok of ['N9A 1A1', 'n9a1a1', ' N9A  1A1 ']) expect(postalIssue(ok), ok).toBeNull()
  })

  it('points at the first wrong character at once', () => {
    expect(postalIssue('6')).toMatchObject({ early: true, message: expect.stringContaining('Character 1 must be a letter') })
    expect(postalIssue('W1A 1A1')).toMatchObject({ early: true }) // W and Z cannot start a code
    expect(postalIssue('D1A 1A1')).toMatchObject({ early: true })
    expect(postalIssue('N9U 1A1')).toMatchObject({ early: true, message: expect.stringContaining('Character 3') })
    expect(postalIssue('NNA 1A1')).toMatchObject({ early: true, message: expect.stringContaining('Character 2 must be a digit') })
    expect(postalIssue('N9A 1A12')).toMatchObject({ early: true })
  })

  it('waits for the rest of an unfinished code', () => {
    expect(postalIssue('N9')).toEqual({ message: 'Enter all 6 characters, e.g. N9A 1A1.', early: false })
  })
})

describe('sanitizeInput: what can be typed', () => {
  const numeric = field('energy_bill_winter')
  it('drops letters, symbols and commas from numbers', () => {
    expect(sanitizeInput(numeric, 'abc12')).toBe('12')
    expect(sanitizeInput(numeric, '$1,500')).toBe('1500')
    expect(sanitizeInput(numeric, '12.5.3')).toBe('12.53') // one decimal point only
    expect(sanitizeInput(numeric, '--5')).toBe('-5')
    expect(sanitizeInput(numeric, '5-3')).toBe('53') // a minus only at the start
  })

  it('keeps a decimal point so a whole-number question can say so, instead of silently changing the number', () => {
    expect(sanitizeInput(field('year_built'), '1985.5')).toBe('1985.5')
  })

  it('upper-cases the postal code, drops other characters and adds the space', () => {
    const postal = field('postal_code')
    expect(sanitizeInput(postal, 'n9a1a1')).toBe('N9A 1A1')
    expect(sanitizeInput(postal, 'n9a')).toBe('N9A')
    expect(sanitizeInput(postal, 'n-9!a 1a1 zzz')).toBe('N9A 1A1')
  })

  it('leaves other questions alone', () => {
    expect(sanitizeInput(field('house_type'), 'Detached  house')).toBe('Detached  house')
  })
})

describe('validate also applies the limits', () => {
  it('reports a value outside its limits, in the units chosen', () => {
    const found = validate(TEST_SPEC, { ...COMPLETE, indoor_temperature: '45' })
    expect(found).toEqual([{ field: 'indoor_temperature', message: 'Enter a value between 10 and 30 °C.' }])
    const imperial = validate(TEST_SPEC, { ...COMPLETE, preferred_units: IMPERIAL, indoor_temperature: '45' })
    expect(imperial[0].message).toBe('Enter a value between 50 and 86 °F.')
  })
})

describe('dropdown questions that stand for a number', () => {
  it('shows the floor area bands in the units the user chose', () => {
    const area = field('floor_area')
    expect(optionLabel(area, TEST_SPEC, {}, AREA.A)).toBe('100–150 m²')
    expect(optionLabel(area, TEST_SPEC, { preferred_units: METRIC }, AREA.A)).toBe('100–150 m²')
    expect(optionLabel(area, TEST_SPEC, { preferred_units: IMPERIAL }, AREA.A)).toBe('1,080–1,610 ft²')
    expect(optionLabel(field('storeys'), TEST_SPEC, { preferred_units: IMPERIAL }, '3')).toBe('3') // same in any unit
  })

  it('reads a chosen band in the review in the chosen units, and a storey count as it is', () => {
    expect(displayValue(field('floor_area'), AREA.A, TEST_SPEC, { preferred_units: IMPERIAL })).toBe('1,080–1,610 ft²')
    expect(displayValue(field('storeys'), '3', TEST_SPEC, {})).toBe('3')
  })

  it('keeps storeys above ground within the total, comparing the numbers the options stand for', () => {
    const rule = 'Storeys above ground cannot be more than the total number of storeys.'
    const above = field('storeys_above_ground')
    expect(fieldIssue(above, '10', TEST_SPEC, { storeys: '9' })?.message).toBe(rule) // "10" is more than "9", as numbers
    expect(fieldIssue(above, '9', TEST_SPEC, { storeys: '10' })).toBeNull()
  })

  it('sends nothing for a dropdown the user left alone', () => {
    const payload = buildPayload(TEST_SPEC, { ...COMPLETE })
    expect(payload).not.toHaveProperty('storeys_above_ground')
  })
})

describe('climate zone must fit the postal code', () => {
  const zone = () => field('zone')

  it('lists the zones for the first letter of the postal code, and says nothing before one is typed', async () => {
    const { zoneIdsForPostalCode } = await import('./formLogic')
    expect(zoneIdsForPostalCode(zone(), { postal_code: 'V6B 1A1' })).toEqual(['zone4'])
    expect(zoneIdsForPostalCode(zone(), { postal_code: ' v' })).toEqual(['zone4'])
    expect(zoneIdsForPostalCode(zone(), {})).toBeNull()
    expect(zoneIdsForPostalCode(zone(), { postal_code: '' })).toBeNull()
    expect(zoneIdsForPostalCode(zone(), { postal_code: 'D1A 1A1' })).toBeNull() // not a real first letter
    expect(zoneIdsForPostalCode(field('storeys'), { postal_code: 'V6B 1A1' })).toBeNull() // not a zone question
  })

  it('reports a zone that does not occur where the postal code is', () => {
    const issue = fieldIssue(zone(), 'Zone 8: Far northern Canada (Yellowknife, Iqaluit)', TEST_SPEC, { postal_code: 'V6B 1A1' })
    expect(issue?.message).toMatch(/does not occur where your postal code is/)
    expect(issue?.early).toBe(true)
  })

  it('accepts a matching zone, or any zone while the postal code gives no hint', () => {
    expect(fieldIssue(zone(), ZONE_A, TEST_SPEC, { postal_code: 'V6B 1A1' })).toBeNull()
    expect(fieldIssue(zone(), ZONE_A, TEST_SPEC, {})).toBeNull()
    expect(fieldIssue(zone(), ZONE_A, TEST_SPEC, { postal_code: 'N9A 1A1' })).toBeNull()
  })

  it('blocks submitting a mismatched zone', () => {
    const problems = validate(TEST_SPEC, { ...COMPLETE, postal_code: 'Y1A 1A1', zone: ZONE_A })
    expect(problems.map((p) => p.field)).toEqual(['zone'])
    expect(validate(TEST_SPEC, { ...COMPLETE, postal_code: 'V6B 1A1', zone: ZONE_A })).toEqual([])
  })
})

describe('renovations and the year built', () => {
  const renovations = field('renovation_history')
  const check = (year: string, built: string | undefined) =>
    fieldIssue(renovations, [{ type: 'Roof', year }], TEST_SPEC, built === undefined ? {} : { year_built: built })

  it('refuses a renovation dated before the building was built', () => {
    expect(check('2005', '2010')).toEqual({ message: 'Renovation 1 is dated before the building was built (2010).', early: true })
  })

  it('accepts the same year or later, or when the year built is not usable yet', () => {
    expect(check('2010', '2010')).toBeNull()
    expect(check('2015', '2010')).toBeNull()
    expect(check('2005', undefined)).toBeNull()
    expect(check('2005', '')).toBeNull()
    expect(check('2005', '1985.5')).toBeNull() // the year built has its own error
  })

  it('names the renovation that is wrong and blocks submitting', () => {
    const answers = { ...COMPLETE, year_built: '2010', renovation_history: [{ type: 'Roof', year: '2015' }, { type: 'Walls', year: '2005' }] }
    expect(validate(TEST_SPEC, answers)).toEqual([
      { field: 'renovation_history', message: 'Renovation 2 is dated before the building was built (2010).' },
    ])
  })
})
