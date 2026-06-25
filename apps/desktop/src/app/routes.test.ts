import { describe, expect, it } from 'vitest'

import { routeSessionProfile, sessionRoute } from './routes'

describe('session routes', () => {
  it('preserves an owning profile in the route query string', () => {
    expect(sessionRoute('telegram/session id', 'ubuntu-server')).toBe('/telegram%2Fsession%20id?profile=ubuntu-server')
    expect(routeSessionProfile('?profile=ubuntu-server')).toBe('ubuntu-server')
  })

  it('omits empty profile hints', () => {
    expect(sessionRoute('session-1', '')).toBe('/session-1')
    expect(routeSessionProfile('')).toBeNull()
  })
})
