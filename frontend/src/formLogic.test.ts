import { describe, expect, it } from 'vitest'
import {
  allFields, arrangePackages, buildPayload, decadeLabel, fieldIssue, initialAnswers, isVisible, money, postalIssue,
  sanitizeInput, validate, zoneIdsForPostalCode,
} from './formLogic'
import { ADVANCED, DEFAULT_WEIGHTS, SIMPLE, TEST_SPEC, ZONE_A, ZONE_B } from './testSpec'
import type { Answers, Package } from './types'

const field = (id: string) => allFields(TEST_SPEC).find((f) => f.id === id)!
const homeFields = TEST_SPEC.sections[0].fields

const COMPLETE: Answers = {
  postal_code: 'n9a 1a1',
  year_built: '1985',
  floor_area: '180',
  zone: ZONE_B,
  budget: '30000',
  preference_mode: SIMPLE,
  priority: 'Balanced outcome',
  weights: { ...DEFAULT_WEIGHTS },
}

describe('initialAnswers', () => {
  it('starts with the preference setting answered and every slider at its default', () => {
    expect(initialAnswers(TEST_SPEC)).toEqual({ preference_mode: SIMPLE, weights: DEFAULT_WEIGHTS })
  })
})

describe('isVisible', () => {
  it('shows the simple or the advanced questions, by the preference setting', () => {
    expect(isVisible(field('priority'), { preference_mode: SIMPLE })).toBe(true)
    expect(isVisible(field('weights'), { preference_mode: SIMPLE })).toBe(false)
    expect(isVisible(field('priority'), { preference_mode: ADVANCED })).toBe(false)
    expect(isVisible(field('weights'), { preference_mode: ADVANCED })).toBe(true)
    expect(isVisible(field('budget'), {})).toBe(true)
  })
})

describe('validate', () => {
  it('accepts a complete form', () => {
    expect(validate(TEST_SPEC, COMPLETE)).toEqual([])
    expect(validate(TEST_SPEC, { ...COMPLETE, preference_mode: ADVANCED, priority: '' })).toEqual([])
  })

  it('asks for every required question that is empty', () => {
    const problems = validate(TEST_SPEC, { preference_mode: SIMPLE })
    expect(problems.map((p) => p.field)).toEqual(['postal_code', 'year_built', 'floor_area', 'zone', 'budget', 'priority'])
    expect(problems[0].message).toBe('Postal code / location is required.')
  })

  it('can check one step only', () => {
    expect(validate(TEST_SPEC, { preference_mode: SIMPLE }, homeFields).map((p) => p.field)).toEqual([
      'postal_code', 'year_built', 'floor_area', 'zone',
    ])
  })

  it('checks postal codes, numbers and whole numbers', () => {
    const problems = validate(TEST_SPEC, { ...COMPLETE, postal_code: 'D1A 1A1', year_built: '1985.5', floor_area: '5000' })
    expect(problems.map((p) => p.field)).toEqual(['postal_code', 'year_built', 'floor_area'])
  })

  it('blocks a mismatched zone', () => {
    expect(validate(TEST_SPEC, { ...COMPLETE, postal_code: 'N9A 1A1', zone: ZONE_A }).map((p) => p.field)).toEqual(['zone'])
  })
})

describe('buildPayload', () => {
  it('sends typed numbers as numbers, chosen options as they are, and tidies the postal code', () => {
    expect(buildPayload(TEST_SPEC, COMPLETE)).toEqual({
      postal_code: 'N9A 1A1',
      year_built: 1985,
      floor_area: 180,
      zone: ZONE_B,
      budget: 30000,
      preference_mode: SIMPLE,
      priority: 'Balanced outcome',
    })
  })

  it('sends the weights, and not the simple questions, in advanced mode', () => {
    const payload = buildPayload(TEST_SPEC, { ...COMPLETE, preference_mode: ADVANCED, weights: { ...DEFAULT_WEIGHTS, payback: 0 } })
    expect(payload.weights).toEqual({ ...DEFAULT_WEIGHTS, payback: 0 })
    expect(payload).not.toHaveProperty('priority')
  })

  it('sends only the criteria the question lists', () => {
    const payload = buildPayload(TEST_SPEC, { ...COMPLETE, preference_mode: ADVANCED, weights: { ...DEFAULT_WEIGHTS, extra: 5 } })
    expect(payload.weights).toEqual(DEFAULT_WEIGHTS)
  })

  it('leaves out empty answers', () => {
    expect(buildPayload(TEST_SPEC, { ...COMPLETE, building_form: '' })).not.toHaveProperty('building_form')
  })
})

describe('fieldIssue: what is wrong with an answer while it is being typed', () => {
  const issue = (id: string, value: string, answers: Answers = {}) => fieldIssue(field(id), value, answers)

  it('says nothing about an empty answer, or one that is fine', () => {
    expect(issue('floor_area', '')).toBeNull()
    expect(issue('floor_area', '180')).toBeNull()
    expect(issue('floor_area', '30')).toBeNull() // the limits themselves are allowed
    expect(issue('floor_area', '1000')).toBeNull()
    expect(issue('floor_area', '180.5')).toBeNull()
  })

  it('shows a value that is too high at once, because typing more cannot fix it', () => {
    expect(issue('floor_area', '1200')).toEqual({ message: 'Enter a value between 30 and 1000.', early: true })
  })

  it('waits before calling a value too small, while more digits may still be coming', () => {
    expect(issue('floor_area', '5')).toMatchObject({ early: false })
    expect(issue('year_built', '18')).toMatchObject({ early: false })
    expect(issue('year_built', '1799')).toMatchObject({ early: true }) // four digits already: too early a year
    expect(issue('budget', '-5')).toMatchObject({ early: true })
  })

  it('writes money with a dollar sign and thousands separators', () => {
    expect(issue('budget', '20000000')!.message).toBe('Enter an amount between $0 and $10,000,000.')
  })

  it('wants whole numbers where the question says so', () => {
    for (const text of ['1985.0', '1985.00', '1985.5']) {
      expect(issue('year_built', text)?.message, text).toBe('Enter a whole number.')
    }
    expect(issue('year_built', '1985')).toBeNull()
    expect(issue('year_built', '1985.')).toBeNull() // a trailing dot is fine while typing
    expect(issue('year_built', '3000')!.message).toBe('Enter a whole number between 1800 and 2026.')
  })

  it('does not accept text where a number belongs', () => {
    expect(issue('budget', 'abc')).toEqual({ message: 'Enter a number.', early: true })
    expect(issue('budget', '-')).toEqual({ message: 'Enter a number.', early: false })
  })

  it('wants every weight a whole number from 0 to 100, and not all of them zero', () => {
    const weights = field('weights')
    expect(fieldIssue(weights, DEFAULT_WEIGHTS, {})).toBeNull()
    expect(fieldIssue(weights, { ...DEFAULT_WEIGHTS, payback: 101 }, {})).not.toBeNull()
    expect(fieldIssue(weights, { initial_cost: 20 }, {})).not.toBeNull() // some missing
    expect(fieldIssue(weights, { initial_cost: 0, energy_savings: 0, payback: 0 }, {})?.message).toBe(
      'Give at least one criterion a weight above 0.',
    )
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
  const numeric = field('budget')
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
    expect(sanitizeInput(field('building_form'), 'Detached  house')).toBe('Detached  house')
  })
})

describe('climate zone must fit the postal code', () => {
  const zone = () => field('zone')

  it('lists the zones for the first letter of the postal code, and says nothing before one is typed', () => {
    expect(zoneIdsForPostalCode(zone(), { postal_code: 'N9A 1A1' })).toEqual(['zone5'])
    expect(zoneIdsForPostalCode(zone(), { postal_code: ' v' })).toEqual(['zone4', 'zone5'])
    expect(zoneIdsForPostalCode(zone(), {})).toBeNull()
    expect(zoneIdsForPostalCode(zone(), { postal_code: 'D1A 1A1' })).toBeNull() // not a real first letter
    expect(zoneIdsForPostalCode(field('building_form'), { postal_code: 'V6B 1A1' })).toBeNull() // not a zone question
  })

  it('reports a zone that does not occur where the postal code is, at once', () => {
    const issue = fieldIssue(zone(), ZONE_A, { postal_code: 'N9A 1A1' })
    expect(issue?.message).toMatch(/does not occur where your postal code is/)
    expect(issue?.early).toBe(true)
  })

  it('accepts a matching zone, or any zone while the postal code gives no hint', () => {
    expect(fieldIssue(zone(), ZONE_A, { postal_code: 'V6B 1A1' })).toBeNull()
    expect(fieldIssue(zone(), ZONE_A, {})).toBeNull()
  })
})

describe('display helpers', () => {
  it('names the decade of a typed year, once it is a whole year', () => {
    expect(decadeLabel('1985')).toBe('1980–1989')
    expect(decadeLabel('2020')).toBe('2020–2029')
    expect(decadeLabel('198')).toBeNull()
    expect(decadeLabel('1985.5')).toBeNull()
    expect(decadeLabel(undefined)).toBeNull()
  })

  it('writes money as whole dollars with separators', () => {
    expect(money(39000)).toBe('$39,000')
    expect(money(1150.6)).toBe('$1,151')
  })
})

describe('arrangePackages: how the recommendations step orders and filters', () => {
  const pkg = (id: string, p: Partial<Package>): Package => ({
    id, name: id, tag: '', description: '', cost: 0, incentive: 0, net_cost: 0, saving_pct: 0, carbon_t: 0,
    embodied_t: 0, payback_yrs: 0, resilience: 0, score: 0, within_budget: true, ...p,
  })
  // Each sort puts these in a different order, so a sort that uses the wrong number shows up.
  const PACKAGES = [
    pkg('a', { score: 0.9, cost: 30000, saving_pct: 20, carbon_t: 2.0, payback_yrs: 5 }),
    pkg('b', { score: 0.7, cost: 10000, saving_pct: 40, carbon_t: 1.0, payback_yrs: 12 }),
    pkg('c', { score: 0.5, cost: 20000, saving_pct: 45, carbon_t: 3.0, payback_yrs: 9, within_budget: false }),
  ]
  const ids = (sort: Parameters<typeof arrangePackages>[1], filter: Parameters<typeof arrangePackages>[2] = 'all') =>
    arrangePackages(PACKAGES, sort, filter).map((p) => p.id)

  it('ranks by the score from the server for "My priorities"', () => {
    expect(ids('personal')).toEqual(['a', 'b', 'c'])
  })

  it('puts the cheapest first, the biggest saver first, the most carbon avoided first and the quickest payback first', () => {
    expect(ids('cost')).toEqual(['b', 'c', 'a'])
    expect(ids('savings')).toEqual(['c', 'b', 'a'])
    expect(ids('carbon')).toEqual(['c', 'a', 'b'])
    expect(ids('payback')).toEqual(['a', 'c', 'b'])
  })

  it('hides packages over budget unless asked to show all', () => {
    expect(ids('personal', 'within')).toEqual(['a', 'b'])
    expect(ids('cost', 'within')).toEqual(['b', 'a'])
    expect(ids('personal', 'all')).toEqual(['a', 'b', 'c'])
  })

  it("never reorders the server's own list, which the results step relies on", () => {
    const before = PACKAGES.map((p) => p.id)
    arrangePackages(PACKAGES, 'cost', 'all')
    arrangePackages(PACKAGES, 'carbon', 'within')
    expect(PACKAGES.map((p) => p.id)).toEqual(before)
  })
})
