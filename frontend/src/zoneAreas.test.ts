import { describe, expect, it } from 'vitest'
import { ZONE_AREAS, ZONE_AREAS_NOTE, ZONE_AREAS_SOURCE } from './zoneAreas'

describe('zoneAreas', () => {
  it('has a unique id, a label and an outline for every zone', () => {
    const ids = ZONE_AREAS.map((z) => z.id)
    expect(ids.length).toBeGreaterThan(0)
    expect(new Set(ids).size).toBe(ids.length)
    for (const zone of ZONE_AREAS) {
      expect(zone.id, zone.id).toMatch(/^zone\w+$/)
      expect(zone.label.length, zone.id).toBeGreaterThan(0)
      expect(zone.d.startsWith('M'), zone.id).toBe(true)
    }
  })

  it('places every label inside the map', () => {
    for (const zone of ZONE_AREAS) {
      expect(zone.lx, zone.id).toBeGreaterThan(0)
      expect(zone.lx, zone.id).toBeLessThan(760)
      expect(zone.ly, zone.id).toBeGreaterThan(0)
      expect(zone.ly, zone.id).toBeLessThan(654)
    }
  })

  it('says where the areas come from, so approximate ones are never mistaken for real ones', () => {
    expect(['approximate', 'real']).toContain(ZONE_AREAS_SOURCE)
    expect(ZONE_AREAS_NOTE.length).toBeGreaterThan(20)
    if (ZONE_AREAS_SOURCE === 'approximate') expect(ZONE_AREAS_NOTE.toLowerCase()).toContain('approximate')
  })
})
