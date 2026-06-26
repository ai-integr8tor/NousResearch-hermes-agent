import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getMessagingPlatforms = vi.fn()
const updateMessagingPlatform = vi.fn()
const restartGateway = vi.fn()
const notify = vi.fn()
const notifyError = vi.fn()

vi.mock('@/hermes', () => ({
  getMessagingPlatforms: () => getMessagingPlatforms(),
  updateMessagingPlatform: (id: string, payload: unknown) => updateMessagingPlatform(id, payload),
  restartGateway: () => restartGateway()
}))

vi.mock('@/store/notifications', () => ({
  notify: (payload: unknown) => notify(payload),
  notifyError: (error: unknown, fallback: string) => notifyError(error, fallback)
}))

function platformFixture() {
  return {
    id: 'discord',
    name: 'Discord',
    description: 'Discord bot integration',
    docs_url: 'https://discord.com/developers',
    state: 'gateway_stopped',
    enabled: true,
    configured: true,
    gateway_running: false,
    error_message: '',
    env_vars: [
      {
        key: 'DISCORD_BOT_TOKEN',
        prompt: 'Bot token',
        description: 'Discord bot token',
        required: true,
        is_password: true,
        is_set: false,
        redacted_value: '',
        url: '',
        advanced: false
      }
    ]
  }
}

function renderMessaging() {
  return import('./index').then(({ MessagingView }) =>
    render(
      <MemoryRouter initialEntries={['/messaging?platform=discord']}>
        <MessagingView />
      </MemoryRouter>
    )
  )
}

beforeEach(() => {
  getMessagingPlatforms.mockResolvedValue({ platforms: [platformFixture()] })
  updateMessagingPlatform.mockResolvedValue({ ok: true })
  restartGateway.mockResolvedValue({ name: 'gateway-restart', pid: 1234 })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('MessagingView restart affordance', () => {
  it('requests restart automatically after saving credentials', async () => {
    await renderMessaging()

    const input = await screen.findByLabelText('Bot token')
    fireEvent.change(input, { target: { value: 'token-123' } })

    const saveButton = screen.getByRole('button', { name: 'Save changes' })
    fireEvent.click(saveButton)

    await waitFor(() => {
      expect(updateMessagingPlatform).toHaveBeenCalledWith('discord', {
        env: { DISCORD_BOT_TOKEN: 'token-123' }
      })
    })

    await waitFor(() => expect(notify).toHaveBeenCalled())

    const successPayload = notify.mock.calls
      .map(call => call[0])
      .find(payload => payload?.title === 'Discord setup saved')

    expect(successPayload).toBeTruthy()
    expect(successPayload.message).toBe('Restart the gateway to reconnect with the new credentials.')
    expect(successPayload.action).toBeUndefined()

    await waitFor(() => expect(restartGateway).toHaveBeenCalledTimes(1))
    expect(notifyError).not.toHaveBeenCalled()
  })
})
