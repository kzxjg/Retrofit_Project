import { describe, expect, it } from 'vitest'
import { PROVINCES, provincesForPostalCode } from './provinceData'

describe('provinceData', () => {
  it('has a unique code, a name and an outline for every province', () => {
    const codes = PROVINCES.map((p) => p.code)
    expect(new Set(codes).size).toBe(codes.length)
    for (const p of PROVINCES) {
      expect(p.name.length, p.code).toBeGreaterThan(0)
      expect(p.d.startsWith('M'), p.code).toBe(true)
    }
  })

  it('maps every postal code letter to provinces that exist on the map', () => {
    const known = new Set(PROVINCES.map((p) => p.code))
    for (const letter of 'ABCEGHJKLMNPRSTVXY') {
      const found = provincesForPostalCode(`${letter}1A 1A1`)
      expect(found.length, letter).toBeGreaterThan(0)
      for (const code of found) expect(known.has(code), `${letter} -> ${code}`).toBe(true)
    }
  })

  it('ignores letters that are not used and empty input', () => {
    expect(provincesForPostalCode('D1A 1A1')).toEqual([])
    expect(provincesForPostalCode('')).toEqual([])
  })

  it('is case-insensitive and tolerates spaces', () => {
    expect(provincesForPostalCode(' n9a 1a1')).toEqual(['ON'])
  })
})
