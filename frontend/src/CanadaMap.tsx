import type { ReactNode } from 'react'
import { MAP_VIEWBOX, PROVINCES } from './provinceData'
import { ZONE_AREAS, ZONE_AREAS_NOTE } from './zoneAreas'

type Props = {
  selectedZoneId: string | null
  onSelectZone: (zoneId: string) => void
  children?: ReactNode // shown under the map, above the note (the zone dropdown)
}

// Light tints so the zones can be told apart before one is chosen (mildest first).
const TINTS = ['#e8edf2', '#dde4eb', '#d2dbe4', '#c7d2de', '#bcc9d7', '#b1c0d0']

export default function CanadaMap({ selectedZoneId, onSelectZone, children }: Props) {
  return (
    <div className="cm">
      <div className="cm-frame">
        <svg viewBox={MAP_VIEWBOX} className="cm-svg" aria-hidden="true">
          {ZONE_AREAS.map((zone, i) => {
            const on = zone.id === selectedZoneId
            return (
              <path
                key={zone.id}
                data-zone={zone.id}
                d={zone.d}
                className={on ? 'cm-zone cm-zone--on' : 'cm-zone'}
                style={on ? undefined : { fill: TINTS[Math.min(i, TINTS.length - 1)] }}
                onClick={() => onSelectZone(zone.id)}
              />
            )
          })}
          {/* province outlines on top, so the shapes are easy to recognise */}
          {PROVINCES.map((province) => (
            <path key={province.code} d={province.d} className="cm-outline" />
          ))}
          {ZONE_AREAS.map((zone) => (
            <text
              key={zone.id}
              x={zone.lx}
              y={zone.ly}
              textAnchor="middle"
              className={zone.id === selectedZoneId ? 'cm-label cm-label--on' : 'cm-label'}
            >
              {zone.label}
            </text>
          ))}
        </svg>
      </div>
      {children}
      <p className="cm-note">{ZONE_AREAS_NOTE}</p>
    </div>
  )
}
