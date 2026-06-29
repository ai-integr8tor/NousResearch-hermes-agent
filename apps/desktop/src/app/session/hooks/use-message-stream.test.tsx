import { QueryClient } from '@tanstack/react-query'
import { act, cleanup, render } from '@testing-library/react'
import type { MutableRefObject } from 'react'
import { useEffect, useRef } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ClientSessionState } from '@/app/types'
import type { ChatMessage } from '@/lib/chat-messages'
import { $clarifyRequests } from '@/store/clarify'
import { $activeSessionId } from '@/store/session'
import type { RpcEvent } from '@/types/hermes'

import { useMessageStream } from './use-message-stream'

const SESSION_ID = 'runtime-session-1'

type Stream = ReturnType<typeof useMessageStream>

interface HarnessHandle {
  getState: (sessionId: string) => ClientSessionState | undefined
  stream: Stream
}

function baseState(overrides: Partial<ClientSessionState> = {}): ClientSessionState {
  return {
    awaitingResponse: true,
    branch: '',
    busy: true,
    cwd: '',
    fast: false,
    interrupted: false,
    messages: [],
    model: '',
    needsInput: false,
    pendingBranchGroup: null,
    personality: '',
    provider: '',
    reasoningEffort: '',
    sawAssistantPayload: false,
    serviceTier: '',
    storedSessionId: 'stored-session-1',
    streamId: null,
    turnStartedAt: Date.now(),
    yolo: false,
    ...overrides
  }
}

function Harness({
  onReady,
  seedMessages = []
}: {
  onReady: (handle: HarnessHandle) => void
  seedMessages?: ChatMessage[]
}) {
  const activeSessionIdRef: MutableRefObject<string | null> = { current: SESSION_ID }
  const statesRef = useRef(new Map<string, ClientSessionState>([[SESSION_ID, baseState({ messages: seedMessages })]]))

  const stream = useMessageStream({
    activeSessionIdRef,
    hydrateFromStoredSession: vi.fn(),
    queryClient: new QueryClient(),
    refreshHermesConfig: vi.fn(async () => undefined),
    refreshSessions: vi.fn(async () => undefined),
    sessionStateByRuntimeIdRef: statesRef,
    updateSessionState: (sessionId, updater, storedSessionId) => {
      const previous = statesRef.current.get(sessionId) ?? baseState()
      const next = updater(previous)
      const withStoredId = storedSessionId ? { ...next, storedSessionId } : next
      statesRef.current.set(sessionId, withStoredId)

      return withStoredId
    }
  })

  useEffect(() => {
    onReady({
      getState: sessionId => statesRef.current.get(sessionId),
      stream
    })
  }, [onReady, stream])

  return null
}

describe('useMessageStream clarify events', () => {
  beforeEach(() => {
    $activeSessionId.set(SESSION_ID)
    $clarifyRequests.set({})
  })

  afterEach(() => {
    cleanup()
    $activeSessionId.set(null)
    $clarifyRequests.set({})
    vi.restoreAllMocks()
  })

  it('adds a pending clarify tool part when the gateway request arrives without a tool.start', () => {
    let handle!: HarnessHandle

    render(<Harness onReady={h => (handle = h)} />)

    act(() => {
      handle.stream.handleGatewayEvent({
        payload: {
          choices: ['Use this chat', 'Start a new one'],
          question: 'Where should I continue?',
          request_id: 'clarify-1'
        },
        session_id: SESSION_ID,
        type: 'clarify.request'
      } satisfies RpcEvent)
    })

    const state = handle.getState(SESSION_ID)
    const message = state?.messages.at(-1)
    const part = message?.parts.at(-1)

    expect(state?.needsInput).toBe(true)
    expect(message).toMatchObject({ pending: true, role: 'assistant' })
    expect(part).toMatchObject({
      args: {
        choices: ['Use this chat', 'Start a new one'],
        question: 'Where should I continue?'
      },
      toolName: 'clarify',
      type: 'tool-call'
    })
    expect(part).not.toHaveProperty('result')
    expect($clarifyRequests.get()[SESSION_ID]).toMatchObject({
      question: 'Where should I continue?',
      requestId: 'clarify-1'
    })
  })

  it('reuses the pending clarify part when tool.start arrives after clarify.request', () => {
    let handle!: HarnessHandle

    render(<Harness onReady={h => (handle = h)} />)

    act(() => {
      handle.stream.handleGatewayEvent({
        payload: {
          choices: ['Use this chat', 'Start a new one'],
          question: 'Where should I continue?',
          request_id: 'clarify-1'
        },
        session_id: SESSION_ID,
        type: 'clarify.request'
      } satisfies RpcEvent)
      handle.stream.handleGatewayEvent({
        payload: {
          args: {
            choices: ['Use this chat', 'Start a new one'],
            question: 'Where should I continue?'
          },
          name: 'clarify',
          tool_id: 'tool-call-1'
        },
        session_id: SESSION_ID,
        type: 'tool.start'
      } satisfies RpcEvent)
    })

    const state = handle.getState(SESSION_ID)

    const clarifyParts = state?.messages.flatMap(message =>
      message.parts.filter(part => part.type === 'tool-call' && part.toolName === 'clarify')
    )

    expect(clarifyParts).toHaveLength(1)
    expect(clarifyParts?.[0]).toMatchObject({
      args: {
        choices: ['Use this chat', 'Start a new one'],
        question: 'Where should I continue?'
      },
      toolCallId: 'tool-call-1',
      toolName: 'clarify',
      type: 'tool-call'
    })
  })
})
