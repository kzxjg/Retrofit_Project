import type { ReactNode } from 'react'
import { MAP_VIEWBOX, PROVINCES } from './provinceData'
import { ZONE_AREAS, ZONE_AREAS_NOTE } from './zoneAreas'

type Props = {
  selectedZoneId: string | null // marked on the map and in the legend; chosen from the list, not the map
  children?: ReactNode // shown under the map, above the note (the zone dropdown)
}

// One blue per zone, from the mildest (lightest) to the coldest (darkest).
export const ZONE_BLUES: Record<string, string> = {
  zone4: '#dcebf7',
  zone5: '#b4d3ee',
  zone6: '#84b4df',
  zone7a: '#5592ca',
  zone7b: '#2d6eac',
  zone8: '#0f477c',
}
const FALLBACK_BLUE = '#9ab8d6'

export function zoneBlue(zoneId: string): string {
  return ZONE_BLUES[zoneId] ?? FALLBACK_BLUE
}

export default function CanadaMap({ selectedZoneId, children }: Props) {
  const selected = ZONE_AREAS.find((zone) => zone.id === selectedZoneId)
  // Coldest first, as on the NECB map.
  const legend = [...ZONE_AREAS].reverse()
  return (
    <div className="cm">
      <figure className="cm-frame">
        <svg viewBox={MAP_VIEWBOX} className="cm-svg" aria-hidden="true">
          {ZONE_AREAS.map((zone) => (
            <path
              key={zone.id}
              data-zone={zone.id}
              d={zone.d}
              className={zone.id === selectedZoneId ? 'cm-zone cm-zone--on' : 'cm-zone'}
              style={{ fill: zoneBlue(zone.id), stroke: zoneBlue(zone.id) }}
            />
          ))}
          {/* province outlines on top, so the shapes are easy to recognise */}
          {PROVINCES.map((province) => (
            <path key={province.code} d={province.d} className="cm-outline" />
          ))}
          {/* the chosen zone's border last, so nothing covers it */}
          {selected && <path d={selected.d} className="cm-ring" />}
        </svg>
        <figcaption className="cm-legend">
          <span className="cm-legend-title">Climate zones</span>
          <ul aria-label="Climate zones">
            {legend.map((zone) => {
              const on = zone.id === selectedZoneId
              return (
                <li key={zone.id} data-legend-zone={zone.id} className={on ? 'cm-key cm-key--on' : 'cm-key'}>
                  <span className="cm-swatch" style={{ background: zoneBlue(zone.id) }} aria-hidden="true" />
                  <span>
                    <strong>Zone {zone.label}</strong> <span className="cm-hdd">{zone.hdd}</span>
                    {on && <span className="cm-yours"> (your zone)</span>}
                  </span>
                </li>
              )
            })}
          </ul>
        </figcaption>
      </figure>
      {children}
      <p className="cm-note">{ZONE_AREAS_NOTE}</p>
    </div>
  )
}
