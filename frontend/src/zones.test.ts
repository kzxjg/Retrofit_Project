import { describe, expect, it } from 'vitest'
import { optionForZoneId, zoneIdFromOption } from './zones'

describe('zones', () => {
  it('turns the text of a zone option into the id the map uses', () => {
    expect(zoneIdFromOption('Zone 4: Mildest; mainly coastal southern BC (Vancouver)')).toBe('zone4')
    expect(zoneIdFromOption('Zone 7A: Prairies (Calgary, Edmonton)')).toBe('zone7a')
    expect(zoneIdFromOption('Zone 7B: Very cold')).toBe('zone7b')
  })

  it('gives nothing for an empty or unrecognised option', () => {
    expect(zoneIdFromOption('')).toBeNull()
    expect(zoneIdFromOption(undefined)).toBeNull()
    expect(zoneIdFromOption('Select…')).toBeNull()
  })

  it('finds the option for a zone id', () => {
    const options = ['Zone 4: a', 'Zone 7A: b', 'Zone 8: c']
    expect(optionForZoneId(options, 'zone7a')).toBe('Zone 7A: b')
    expect(optionForZoneId(options, 'zone9')).toBeUndefined()
  })
})
