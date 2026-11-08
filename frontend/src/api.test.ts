import { afterEach, describe, expect, it, vi } from 'vitest'

function mockFetch() {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    void url
    void init
    return { ok: true, status: 200, json: async () => ({ sections: [] }) }
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

// the address is read when the file is first loaded, so load a fresh copy for each setting
async function loadApi() {
  vi.resetModules()
  return import('./api')
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('where the page sends its requests', () => {
  it('uses the page\'s own address when no server address is set', async () => {
    vi.stubEnv('VITE_API_URL', '')
    const fetchMock = mockFetch()
    const api = await loadApi()
    await api.fetchSpec()
    await api.submitAnswers({ a: 1 })
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/form-spec', '/api/recommend'])
  })

  it('goes to the server address when one is set, with or without a trailing slash', async () => {
    for (const setting of ['https://api.example.org', 'https://api.example.org/', 'https://api.example.org//']) {
      vi.stubEnv('VITE_API_URL', setting)
      const fetchMock = mockFetch()
      const api = await loadApi()
      await api.fetchSpec()
      await api.submitAnswers({ a: 1 })
      expect(fetchMock.mock.calls.map(([url]) => url), setting).toEqual([
        'https://api.example.org/api/form-spec',
        'https://api.example.org/api/recommend',
      ])
    }
  })
})

describe('answers from the server', () => {
  async function submitWith(response: { ok: boolean; status: number; json: () => Promise<unknown> }) {
    vi.stubEnv('VITE_API_URL', '')
    vi.stubGlobal('fetch', vi.fn(async () => response))
    const api = await loadApi()
    return api.submitAnswers({ postal_code: 'N9A 1A1' })
  }

  it('hands back the report on a 200', async () => {
    const report = { packages: [{ id: 'basic' }] }
    expect(await submitWith({ ok: true, status: 200, json: async () => report })).toEqual({ ok: true, report })
  })

  it('turns a 422 into its list of errors', async () => {
    const errors = [{ field: 'zone', message: 'No.' }]
    expect(await submitWith({ ok: false, status: 422, json: async () => ({ errors }) })).toEqual({ ok: false, errors })
  })

  it('gives a generic error when a 422 body cannot be read', async () => {
    const outcome = await submitWith({ ok: false, status: 422, json: async () => { throw new Error('bad json') } })
    expect(outcome).toEqual({ ok: false, errors: [{ field: '', message: 'The server rejected the answers.' }] })
  })

  it.each([403, 413, 415, 500])('throws on a %i so the page can say the server could not be used', async (status) => {
    await expect(submitWith({ ok: false, status, json: async () => ({}) })).rejects.toThrow(String(status))
  })

  it('passes on the server\'s own wording when there are too many requests', async () => {
    const message = 'Too many requests. Please wait a minute and try again.'
    const error = await submitWith({ ok: false, status: 429, json: async () => ({ errors: [{ field: '', message }] }) })
      .catch((err: unknown) => err)
    // submitWith loads a fresh copy of api.ts, so compare by name rather than with instanceof
    expect(error).toMatchObject({ name: 'ServerMessage', message, status: 429 })
  })

  it.each([
    ['an unreadable body', async () => { throw new Error('bad json') }],
    ['no errors list', async () => ({})],
    ['an empty errors list', async () => ({ errors: [] })],
    ['a message that is not text', async () => ({ errors: [{ field: '', message: 42 }] })],
    ['a blank message', async () => ({ errors: [{ field: '', message: '   ' }] })],
  ])('falls back to a friendly message on a 429 with %s', async (_case, json) => {
    await expect(submitWith({ ok: false, status: 429, json })).rejects.toThrow(
      'Too many requests. Please wait a minute and try again.',
    )
  })

  it('cuts a very long 429 message down to size', async () => {
    const outcome = submitWith({ ok: false, status: 429, json: async () => ({ errors: [{ field: '', message: 'x'.repeat(5000) }] }) })
    const error = (await outcome.catch((err: unknown) => err)) as Error
    expect(error.message).toHaveLength(300)
  })

  it('lets a network failure through as an error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network down') }))
    const api = await loadApi()
    await expect(api.submitAnswers({})).rejects.toThrow('network down')
  })

  it('sends no CSRF token: the API does not use one', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ packages: [] }) }))
    vi.stubGlobal('fetch', fetchMock)
    const api = await loadApi()
    document.cookie = 'csrftoken=abc%20123'
    await api.submitAnswers({})
    expect(JSON.stringify((fetchMock.mock.calls[0] as unknown[])[1])).not.toContain('X-CSRFToken')
    document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  })
})
