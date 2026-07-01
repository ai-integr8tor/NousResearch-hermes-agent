import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createCronJob,
  deleteCronJob,
  getCronJob,
  getCronJobRuns,
  getCronJobs,
  getSessionMessages,
  listAllProfileSessions,
  listSessions,
  pauseCronJob,
  resumeCronJob,
  setApiRequestProfile,
  triggerCronJob,
  updateCronJob
} from './hermes'

const emptySessionsResponse = {
  limit: 0,
  offset: 0,
  sessions: [],
  total: 0
}

describe('Hermes REST session helpers', () => {
  let api: ReturnType<typeof vi.fn>

  beforeEach(() => {
    api = vi.fn().mockResolvedValue(emptySessionsResponse)
    Object.defineProperty(window, 'hermesDesktop', {
      configurable: true,
      value: { api }
    })
  })

  afterEach(() => {
    setApiRequestProfile(null)
    vi.restoreAllMocks()
    Reflect.deleteProperty(window, 'hermesDesktop')
  })

  it('uses a longer timeout for the single-profile session list', async () => {
    await listSessions(50, 1)

    expect(api).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/api/sessions?limit=50&offset=0&min_messages=1&archived=exclude&order=recent',
        timeoutMs: 60_000
      })
    )
  })

  it('uses a longer timeout for the all-profile session list', async () => {
    await listAllProfileSessions(50, 1)

    expect(api).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/api/profiles/sessions?limit=50&offset=0&min_messages=1&archived=exclude&order=recent&profile=all',
        timeoutMs: 60_000
      })
    )
  })

  it('tags cross-profile message reads for Electron routing and backend lookup', async () => {
    api.mockResolvedValue({ messages: [], session_id: 'session-1' })

    await getSessionMessages('session-1', 'xiaoxuxu')

    expect(api).toHaveBeenCalledWith({
      path: '/api/sessions/session-1/messages?profile=xiaoxuxu',
      profile: 'xiaoxuxu'
    })
  })

  it('tags cron job reads and mutations with the active API profile', async () => {
    setApiRequestProfile('worker_alpha')
    api.mockResolvedValue({ runs: [] })

    await getCronJobs()
    await getCronJob('job 1')
    await getCronJobRuns('job 1', 7)
    await createCronJob({ name: 'Daily', prompt: 'say hi', schedule: '0 9 * * *' })
    await updateCronJob('job 1', { paused: true })
    await pauseCronJob('job 1')
    await resumeCronJob('job 1')
    await triggerCronJob('job 1')
    await deleteCronJob('job 1')

    expect(api).toHaveBeenNthCalledWith(1, {
      path: '/api/cron/jobs',
      profile: 'worker_alpha'
    })
    expect(api).toHaveBeenNthCalledWith(2, {
      path: '/api/cron/jobs/job%201',
      profile: 'worker_alpha'
    })
    expect(api).toHaveBeenNthCalledWith(3, {
      path: '/api/cron/jobs/job%201/runs?limit=7',
      profile: 'worker_alpha'
    })
    expect(api).toHaveBeenNthCalledWith(4, {
      path: '/api/cron/jobs',
      method: 'POST',
      body: { name: 'Daily', prompt: 'say hi', schedule: '0 9 * * *' },
      profile: 'worker_alpha'
    })
    expect(api).toHaveBeenNthCalledWith(5, {
      path: '/api/cron/jobs/job%201',
      method: 'PUT',
      body: { updates: { paused: true } },
      profile: 'worker_alpha'
    })
    expect(api).toHaveBeenNthCalledWith(6, {
      path: '/api/cron/jobs/job%201/pause',
      method: 'POST',
      profile: 'worker_alpha'
    })
    expect(api).toHaveBeenNthCalledWith(7, {
      path: '/api/cron/jobs/job%201/resume',
      method: 'POST',
      profile: 'worker_alpha'
    })
    expect(api).toHaveBeenNthCalledWith(8, {
      path: '/api/cron/jobs/job%201/trigger',
      method: 'POST',
      profile: 'worker_alpha'
    })
    expect(api).toHaveBeenNthCalledWith(9, {
      path: '/api/cron/jobs/job%201',
      method: 'DELETE',
      profile: 'worker_alpha'
    })
  })
})
