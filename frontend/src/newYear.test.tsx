// What happens to the year-built limit when the calendar turns over. The server moves its limit
// forward on January 1 (recommendations/tests.py, test_limits_move_forward_on_new_year); this checks
// the page follows the server rather than its own clock.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fieldIssue } from './formLogic'
import { TEST_SPEC } from './testSpec'

const yearBuiltField = TEST_SPEC.sections.flatMap((s) => s.fields).find((f) => f.id === 'year_built')!

afterEach(() => {
  vi.useRealTimers()
})

describe('year built', () => {
  it("uses the server's maximum, so a home finished this new year is accepted once the server says so", () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2027, 0, 1))
    const lastYear = { ...yearBuiltField, max: 2026 }
    const thisYear = { ...yearBuiltField, max: 2027 }
    expect(fieldIssue(lastYear, '2027', {})).not.toBeNull()
    expect(fieldIssue(thisYear, '2027', {})).toBeNull()
  })
})
