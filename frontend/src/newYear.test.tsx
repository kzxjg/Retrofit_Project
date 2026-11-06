// What happens to year limits when the calendar turns over. The server moves its limits forward
// on January 1 (recommendations/tests.py, test_limits_move_forward_on_new_year); these check the
// page follows the server, and that its own fallback follows the clock.
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Renovations from './Renovations'
import { fieldIssue } from './formLogic'
import { TEST_SPEC } from './testSpec'
import type { Field } from './types'

const renovationField = TEST_SPEC.sections.flatMap((s) => s.fields).find((f) => f.type === 'records')!
const yearBuiltField = TEST_SPEC.sections.flatMap((s) => s.fields).find((f) => f.id === 'year_built')!

function yearsOffered(field: Field) {
  render(<Renovations field={field} records={[{ type: '', year: '' }]} onChange={() => {}} />)
  const select = screen.getByLabelText('Renovation 1 year')
  return within(select)
    .getAllByRole('option')
    .map((o) => o.getAttribute('value'))
    .filter(Boolean)
    .map(Number)
}

afterEach(() => {
  vi.useRealTimers()
})

describe('renovation years', () => {
  it("offers exactly the server's range, newest first, whatever the browser's clock says", () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 11, 31, 23, 59))
    const years = yearsOffered({ ...renovationField, year_range: [2020, 2027] })
    expect(years[0]).toBe(2027) // the server has already moved on; the page shows its year
    expect(years.at(-1)).toBe(2020)
    expect(years).toHaveLength(8)
  })

  it('falls back to this year from the clock when the server gives no range', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 11, 31, 23, 59))
    const { year_range: _omit, ...withoutRange } = renovationField
    void _omit
    expect(yearsOffered(withoutRange)[0]).toBe(2026)
  })

  it('offers the new year from January 1 when it falls back to the clock', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2027, 0, 1, 0, 0, 1))
    const { year_range: _omit, ...withoutRange } = renovationField
    void _omit
    const years = yearsOffered(withoutRange)
    expect(years[0]).toBe(2027)
    expect(years.at(-1)).toBe(1900)
  })

  it('can choose a renovation dated in the newest year offered', () => {
    const onChange = vi.fn()
    render(
      <Renovations
        field={{ ...renovationField, year_range: [2020, 2027] }}
        records={[{ type: '', year: '' }]}
        onChange={onChange}
      />,
    )
    fireEvent.change(screen.getByLabelText('Renovation 1 year'), { target: { value: '2027' } })
    expect(onChange).toHaveBeenCalledWith([{ type: '', year: '2027' }])
  })
})

describe('year built', () => {
  it("uses the server's maximum, so a home finished this new year is accepted once the server says so", () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2027, 0, 1))
    const lastYear = { ...yearBuiltField, max: 2026 }
    const thisYear = { ...yearBuiltField, max: 2027 }
    expect(fieldIssue(lastYear, '2027', TEST_SPEC, {})).not.toBeNull()
    expect(fieldIssue(thisYear, '2027', TEST_SPEC, {})).toBeNull()
  })
})
