import type { ApiError, Incentive, Spec } from './types'

// Where the Django server is. Leave it empty and the page calls the server at its own address, which
// is how the development server (it forwards /api to Django) and a site served from one domain work.
// Set VITE_API_URL (for example to https://api.example.org) when the page is hosted somewhere else.
const API_URL = String(import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')

export async function fetchSpec(): Promise<Spec> {
  const response = await fetch(`${API_URL}/api/form-spec`)
  if (!response.ok) throw new Error(`Server returned ${response.status}`)
  return (await response.json()) as Spec
}

export async function fetchIncentives(zone: string): Promise<Incentive[]> {
  const response = await fetch(`${API_URL}/api/incentives?zone=${encodeURIComponent(zone)}`)
  if (!response.ok) throw new Error(`Server returned ${response.status}`)
  const data = (await response.json()) as { programs: Incentive[] }
  return data.programs
}

// A problem the user can act on, with the server's own wording, e.g. "Too many requests. Please
// wait a minute and try again." The page shows its message as it is.
export class ServerMessage extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ServerMessage'
    this.status = status
  }
}

const TOO_MANY_REQUESTS = 'Too many requests. Please wait a minute and try again.'

// The first error message in a response like {"errors": [{"field": "", "message": "..."}]}.
async function firstMessage(response: Response): Promise<string | null> {
  try {
    const data = (await response.json()) as { errors?: { message?: unknown }[] }
    const message = Array.isArray(data.errors) ? data.errors[0]?.message : undefined
    return typeof message === 'string' && message.trim() ? message.trim().slice(0, 300) : null
  } catch {
    return null
  }
}

export type SubmitOutcome =
  | { ok: true; recommendation: string }
  | { ok: false; errors: ApiError[] }

export async function submitAnswers(answers: Record<string, unknown>): Promise<SubmitOutcome> {
  const response = await fetch(`${API_URL}/api/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers }),
  })
  if (response.ok) {
    const data = (await response.json()) as { package: string }
    return { ok: true, recommendation: data.package }
  }
  if (response.status === 422) {
    try {
      const data = (await response.json()) as { errors?: ApiError[] }
      if (Array.isArray(data.errors)) return { ok: false, errors: data.errors }
    } catch {
      // fall through to the generic message below
    }
    return { ok: false, errors: [{ field: '', message: 'The server rejected the answers.' }] }
  }
  if (response.status === 429) {
    throw new ServerMessage((await firstMessage(response)) ?? TOO_MANY_REQUESTS, 429)
  }
  throw new Error(`Server returned ${response.status}`)
}
