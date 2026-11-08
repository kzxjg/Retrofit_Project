import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import FieldControl from './FieldControl'
import { CRITERIA, DEFAULT_WEIGHTS } from './testSpec'
import type { Field } from './types'

const area: Field = { id: 'floor_area', label: 'Floor area', type: 'number', required: true, min: 30, max: 1000, help: 'Heated area only.' }
const weights: Field = { id: 'weights', label: 'Criteria weights', type: 'weights', required: true, min: 0, max: 100, criteria: CRITERIA, help: 'Values are normalized.' }
const longSelect: Field = { id: 'zone', label: 'Climate zone', type: 'select', required: true, options: ['Zone 4: a long description of the mildest zone in the country', 'Zone 5'] }

describe('FieldControl: what screen readers are told', () => {
  it('links the help text, and marks nothing invalid while there is no error', () => {
    render(<FieldControl field={area} answers={{}} onChange={() => {}} />)
    const box = screen.getByLabelText('Floor area')
    expect(box).toHaveAccessibleDescription('Heated area only.')
    expect(box).not.toHaveAttribute('aria-invalid')
  })

  it('marks the answer invalid and reads the help and the error together', () => {
    render(<FieldControl field={area} answers={{ floor_area: '2' }} onChange={() => {}} error="Enter a value between 30 and 1000." />)
    const box = screen.getByLabelText('Floor area')
    expect(box).toHaveAttribute('aria-invalid', 'true')
    expect(box).toHaveAccessibleDescription('Heated area only. Enter a value between 30 and 1000.')
  })

  it('describes the group of sliders with its help and its error', () => {
    render(<FieldControl field={weights} answers={{ weights: DEFAULT_WEIGHTS }} onChange={() => {}} error="Give at least one criterion a weight above 0." />)
    expect(screen.getByRole('group', { name: 'Criteria weights' })).toHaveAccessibleDescription(
      'Values are normalized. Give at least one criterion a weight above 0.',
    )
  })
})

describe('FieldControl: answering', () => {
  it('moves only the slider that was dragged, keeping the others', () => {
    const onChange = vi.fn()
    render(<FieldControl field={weights} answers={{ weights: DEFAULT_WEIGHTS }} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Payback'), { target: { value: '70' } })
    expect(onChange).toHaveBeenCalledWith('weights', { ...DEFAULT_WEIGHTS, payback: 70 })
  })

  it('tidies what is typed before passing it on', () => {
    const onChange = vi.fn()
    render(<FieldControl field={area} answers={{}} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Floor area'), { target: { value: '1,8a0' } })
    expect(onChange).toHaveBeenCalledWith('floor_area', '180')
  })

  it('shows a long chosen option in full under the dropdown', () => {
    const chosen = longSelect.options![0]
    const { container } = render(<FieldControl field={longSelect} answers={{ zone: chosen }} onChange={() => {}} />)
    expect(container.querySelector('.pg-selected')).toHaveTextContent(chosen)
    // already answered, so there is no blank "Select…" choice
    expect(screen.queryByRole('option', { name: 'Select…' })).toBeNull()
  })
})
