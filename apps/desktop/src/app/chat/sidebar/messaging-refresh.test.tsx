import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SidebarProvider } from '@/components/ui/sidebar'
import { I18nProvider } from '@/i18n'
import { $sidebarMessagingOpenIds } from '@/store/layout'
import { $profiles } from '@/store/profile'
import {
  $messagingSessions,
  $sessions,
  $sessionsLoading,
  setMessagingSessions,
  setSessions,
  setSessionsLoading
} from '@/store/session'
import type { SessionInfo } from '@/types/hermes'

vi.mock('@/hermes', async importOriginal => {
  const actual = await importOriginal<typeof import('@/hermes')>()

  return {
    ...actual,
    searchSessions: vi.fn().mockResolvedValue({ results: [] })
  }
})

import { ChatSidebar } from './index'

function mockSession(id: string, source: string): SessionInfo {
  const now = Date.now()

  return {
    ended_at: null,
    id,
    input_tokens: 0,
    is_active: false,
    last_active: now,
    message_count: 1,
    model: null,
    output_tokens: 0,
    preview: 'hello',
    source,
    started_at: now,
    title: 'Test chat',
    tool_call_count: 0
  }
}

function noop() {
  return undefined
}

function renderSidebar(onRefreshMessaging?: () => void | Promise<void>) {
  return render(
    <MemoryRouter>
      <I18nProvider configClient={null}>
        <SidebarProvider>
          <ChatSidebar
            currentView="chat"
            onArchiveSession={noop}
            onDeleteSession={noop}
            onLoadMoreSessions={noop}
            onManageCronJob={noop}
            onNavigate={noop}
            onNewSessionInWorkspace={noop}
            onRefreshMessaging={onRefreshMessaging}
            onResumeSession={noop}
            onTriggerCronJob={noop}
          />
        </SidebarProvider>
      </I18nProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  $profiles.set([])
  setSessions([mockSession('local-1', 'desktop')])
  setSessionsLoading(false)
  setMessagingSessions([mockSession('tg-1', 'telegram')])
  $sidebarMessagingOpenIds.set([])
})

afterEach(() => {
  cleanup()
  $profiles.set([])
  setSessions([])
  setMessagingSessions([])
  setSessionsLoading(false)
  $sidebarMessagingOpenIds.set([])
  $sessions.set([])
  $messagingSessions.set([])
})

describe('ChatSidebar messaging refresh', () => {
  it('renders a refresh button on each messaging platform section', () => {
    setMessagingSessions([mockSession('tg-1', 'telegram'), mockSession('dc-1', 'discord')])

    renderSidebar(noop)

    expect(screen.getAllByRole('button', { name: 'Refresh gateway sessions' })).toHaveLength(2)
  })

  it('calls onRefreshMessaging once when the refresh button is clicked', async () => {
    const onRefreshMessaging = vi.fn().mockResolvedValue(undefined)

    renderSidebar(onRefreshMessaging)

    fireEvent.click(screen.getAllByRole('button', { name: 'Refresh gateway sessions' })[0]!)

    await waitFor(() => expect(onRefreshMessaging).toHaveBeenCalledTimes(1))
  })

  it('does not render refresh buttons when onRefreshMessaging is omitted', () => {
    renderSidebar()

    expect(screen.queryByRole('button', { name: 'Refresh gateway sessions' })).toBeNull()
  })

  it('disables refresh buttons while onRefreshMessaging is in flight', async () => {
    let resolveRefresh: (() => void) | undefined
    const onRefreshMessaging = vi.fn(
      () =>
        new Promise<void>(resolve => {
          resolveRefresh = resolve
        })
    )

    setMessagingSessions([mockSession('tg-1', 'telegram'), mockSession('dc-1', 'discord')])
    renderSidebar(onRefreshMessaging)

    fireEvent.click(screen.getAllByRole('button', { name: 'Refresh gateway sessions' })[0]!)

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: 'Refreshing gateway sessions' })).toHaveLength(2)
      for (const button of screen.getAllByRole('button', { name: 'Refreshing gateway sessions' })) {
        expect((button as HTMLButtonElement).disabled).toBe(true)
      }
    })
    expect(onRefreshMessaging).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveRefresh?.()
    })

    await waitFor(() => {
      for (const button of screen.getAllByRole('button', { name: 'Refresh gateway sessions' })) {
        expect((button as HTMLButtonElement).disabled).toBe(false)
      }
    })
  })
})