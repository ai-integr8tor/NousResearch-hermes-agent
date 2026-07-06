import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SlashReferenceApp } from './slash-reference-app'

describe('SlashReferenceApp', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    Object.defineProperty(window, 'hermesDesktop', {
      configurable: true,
      value: undefined
    })
  })

  it('copies clicked slash commands through the desktop clipboard bridge', async () => {
    const writeClipboard = vi.fn().mockResolvedValue(true)
    Object.defineProperty(window, 'hermesDesktop', {
      configurable: true,
      value: { writeClipboard }
    })

    render(<SlashReferenceApp />)

    fireEvent.click(screen.getByRole('button', { name: /^Copy \/start/ }))

    await waitFor(() => expect(writeClipboard).toHaveBeenCalledWith('/start'))
    expect(screen.getByText('/start copied')).toBeTruthy()
  })

  it('renders cheat-sheet copy without raw argument hints in the visible rows', () => {
    render(<SlashReferenceApp />)

    const newCommand = screen.getByRole('button', { name: /^Copy \/new/ })

    expect(screen.getByText('Tags')).toBeTruthy()
    expect(screen.getAllByText('BOTH').length).toBeGreaterThan(0)
    expect(screen.getByText('CLI + chat')).toBeTruthy()
    expect(newCommand.textContent).toContain('/new')
    expect(newCommand.textContent).toContain('Start a new session')
    expect(newCommand.textContent).toContain('aka /reset')
    expect(newCommand.textContent).not.toContain('[name]')
  })

  it('keeps long aliases trimmed in the compact menu rows', () => {
    render(<SlashReferenceApp />)

    const backgroundCommand = screen.getByRole('button', { name: /^Copy \/background/ })
    const codexRuntimeCommand = screen.getByRole('button', { name: /^Copy \/codex-runtime/ })
    const journeyCommand = screen.getByRole('button', { name: /^Copy \/journey/ })

    expect(backgroundCommand.textContent).toContain('aka /bg')
    expect(backgroundCommand.textContent).not.toContain('/btw')
    expect(codexRuntimeCommand.textContent).not.toContain('/codex_runtime')
    expect(journeyCommand.textContent).toContain('aka /learning')
    expect(journeyCommand.textContent).not.toContain('/memory-graph')
  })
})
