import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ResultsStep } from './ReportSteps'
import { TEST_REPORT } from './testSpec'
import type { Package } from './types'

// The bar inside each role="img" track is drawn by its width.
const barWidth = (label: string) => (screen.getByRole('img', { name: label }).firstElementChild as HTMLElement).style.width

describe('ResultsStep: the savings bars', () => {
  it('draws each bar as wide as its percentage', () => {
    const chosen = TEST_REPORT.packages[1]
    render(<ResultsStep report={TEST_REPORT} chosen={chosen} />)
    for (const p of TEST_REPORT.packages) {
      expect(barWidth(`${p.name}: ${p.saving_pct}% energy savings`)).toBe(`${p.saving_pct}%`)
    }
    expect(barWidth(`${chosen.saving_pct}% of operational emissions`)).toBe(`${chosen.saving_pct}%`)
  })

  it('never draws a bar past the end of its track, even if a saving were over 100%', () => {
    const huge: Package = { ...TEST_REPORT.packages[0], saving_pct: 140 }
    const report = { ...TEST_REPORT, packages: [huge] }
    render(<ResultsStep report={report} chosen={huge} />)
    expect(barWidth(`${huge.name}: 140% energy savings`)).toBe('100%')
    expect(barWidth('140% of operational emissions')).toBe('100%')
    // the number itself is still shown as the server sent it
    expect(screen.getAllByText('140%')).toHaveLength(2)
  })
})
