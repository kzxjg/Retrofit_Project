import { useEffect, useState } from 'react'
import { fetchIncentives } from './api'
import type { Field, Incentive } from './types'

type Props = {
  field: Field
  zone: string
  selected: string[]
  onChange: (next: string[]) => void
}

export default function Incentives({ field, zone, selected, onChange }: Props) {
  const [programs, setPrograms] = useState<Incentive[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')

  useEffect(() => {
    if (!zone) {
      setPrograms([])
      setStatus('idle')
      return
    }
    let cancelled = false
    setStatus('loading')
    fetchIncentives(zone)
      .then((list) => {
        if (!cancelled) {
          setPrograms(list)
          setStatus('idle')
        }
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [zone])

  function toggle(name: string) {
    onChange(selected.includes(name) ? selected.filter((n) => n !== name) : [...selected, name])
  }

  return (
    <fieldset className="pg-group">
      <legend className="pg-field-title">{field.label}</legend>
      {field.help && <p className="pg-help">{field.help}</p>}

      {!zone && <p className="pg-help">Choose a zone to see the programs that may apply.</p>}
      {status === 'loading' && <p className="pg-help">Loading programs…</p>}
      {status === 'error' && <p className="pg-help">Could not load the programs. Try again later.</p>}
      {zone && status === 'idle' && programs.length === 0 && (
        <p className="pg-help">No programs are listed for this zone yet.</p>
      )}

      {programs.map((program) => (
        <label key={program.id} className="pg-program">
          <input
            type="checkbox"
            checked={selected.includes(program.name)}
            onChange={() => toggle(program.name)}
          />
          <span>
            <strong>{program.name}</strong>
            <span className="pg-program-line">Eligibility: {program.eligibility}</span>
            <span className="pg-program-line">Amount: {program.amount}</span>
            <span className="pg-program-line">Deadline: {program.deadline}</span>
            <span className="pg-program-line">
              Last verified: {program.last_verified ?? 'not yet verified'}
            </span>
          </span>
        </label>
      ))}
    </fieldset>
  )
}
