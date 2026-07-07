import { cleanup, render, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getCronJobs, listAllProfileSessions, type SessionInfo } from '@/hermes'
import { $pinnedSessionIds } from '@/store/layout'
import {
  $sessions,
  setCronSessions,
  setMessagingSessions,
  setSessions
} from '@/store/session'

import { useSessionListActions } from './use-session-list-actions'

vi.mock('@/hermes', async importOriginal => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getCronJobs: vi.fn(),
  listAllProfileSessions: vi.fn()
}))

function session(overrides: Partial<SessionInfo>): SessionInfo {
  return {
    archived: false,
    cwd: null,
    ended_at: null,
    id: 'session',
    input_tokens: 0,
    is_active: false,
    last_active: 1,
    message_count: 1,
    model: null,
    output_tokens: 0,
    preview: null,
    source: 'desktop',
    started_at: 1,
    title: null,
    tool_call_count: 0,
    ...overrides
  }
}

function Harness({ onReady }: { onReady: (refresh: () => Promise<void>) => void }) {
  const actions = useSessionListActions({ profileScope: 'default' })

  useEffect(() => {
    onReady(actions.refreshSessions)
  }, [actions.refreshSessions, onReady])

  return null
}

describe('useSessionListActions pinned session hydration', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    $pinnedSessionIds.set([])
    setSessions([])
    setCronSessions([])
    setMessagingSessions([])
  })

  it('hydrates a pinned row missing from the bounded recent page', async () => {
    $pinnedSessionIds.set(['old-pinned'])

    vi.mocked(getCronJobs).mockResolvedValue([])
    vi.mocked(listAllProfileSessions).mockImplementation(
      async (_limit, _minMessages, _archived, _order, _profile, filter = {}) => {
        if (filter.ids?.includes('old-pinned')) {
          return {
            limit: 1,
            offset: 0,
            sessions: [session({ id: 'old-pinned', title: 'Pinned but old' })],
            total: 1
          }
        }

        if (filter.source === 'cron' || filter.excludeSources) {
          return { limit: 1, offset: 0, sessions: [], total: 0 }
        }

        return {
          limit: 1,
          offset: 0,
          sessions: [session({ id: 'recent', title: 'Recent' })],
          total: 2
        }
      }
    )

    let refresh: (() => Promise<void>) | null = null
    render(<Harness onReady={fn => (refresh = fn)} />)
    await waitFor(() => expect(refresh).not.toBeNull())

    await refresh!()

    await waitFor(() => {
      expect($sessions.get().map(s => s.id)).toEqual(['old-pinned', 'recent'])
    })
    expect(vi.mocked(listAllProfileSessions)).toHaveBeenCalledWith(
      1,
      0,
      'exclude',
      'recent',
      'default',
      { ids: ['old-pinned'] }
    )
  })

  it('does not refetch a pin already loaded by lineage root', async () => {
    $pinnedSessionIds.set(['root-id'])
    setSessions([session({ id: 'tip-id', _lineage_root_id: 'root-id' })])

    vi.mocked(getCronJobs).mockResolvedValue([])
    vi.mocked(listAllProfileSessions).mockResolvedValue({
      limit: 1,
      offset: 0,
      sessions: [session({ id: 'tip-id', _lineage_root_id: 'root-id' })],
      total: 1
    })

    let refresh: (() => Promise<void>) | null = null
    render(<Harness onReady={fn => (refresh = fn)} />)
    await waitFor(() => expect(refresh).not.toBeNull())

    await refresh!()

    expect(vi.mocked(listAllProfileSessions)).not.toHaveBeenCalledWith(
      expect.any(Number),
      0,
      'exclude',
      'recent',
      'default',
      { ids: ['root-id'] }
    )
  })
})
