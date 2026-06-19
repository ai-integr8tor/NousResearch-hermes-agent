import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'

import { modelOptionsQueryKey } from './model-options-query'

describe('modelOptionsQueryKey', () => {
  it('isolates configured-only model options from full-universe options', () => {
    const client = new QueryClient()
    const allPayload = {
      providers: [
        { name: 'Anthropic', slug: 'anthropic', models: ['claude-opus'], authenticated: true }
      ],
      provider: 'opencode-go',
      model: 'glm-5.2'
    }
    const configuredPayload = {
      providers: [
        { name: 'OpenCode Go', slug: 'opencode-go', models: ['glm-5.2'], authenticated: true }
      ],
      provider: 'opencode-go',
      model: 'glm-5.2'
    }

    client.setQueryData(modelOptionsQueryKey('all', 'session-1'), allPayload)

    expect(client.getQueryData(modelOptionsQueryKey('configured', 'session-1'))).toBeUndefined()

    client.setQueryData(modelOptionsQueryKey('configured', 'session-1'), configuredPayload)

    expect(client.getQueryData(modelOptionsQueryKey('all', 'session-1'))).toBe(allPayload)
    expect(client.getQueryData(modelOptionsQueryKey('configured', 'session-1'))).toBe(configuredPayload)
  })

  it('uses stable global keys for pre-session pickers', () => {
    expect(modelOptionsQueryKey('configured')).toEqual(['model-options', 'configured', 'global'])
    expect(modelOptionsQueryKey('all', null)).toEqual(['model-options', 'all', 'global'])
  })
})
