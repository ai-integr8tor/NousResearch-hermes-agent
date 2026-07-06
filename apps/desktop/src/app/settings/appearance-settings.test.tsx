import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const setMenuBarCommandReferenceEnabled = vi.fn()

vi.mock('@/themes/context', () => ({
  getBaseColors: () => ({
    background: '#000000',
    border: '#333333',
    foreground: '#ffffff',
    muted: '#111111',
    mutedForeground: '#aaaaaa'
  }),
  useTheme: () => ({
    availableThemes: [],
    mode: 'dark',
    resolvedMode: 'dark',
    setMode: vi.fn(),
    setTheme: vi.fn(),
    themeName: 'nous'
  })
}))

vi.mock('@/themes/install', () => ({
  installVscodeThemeFromMarketplace: vi.fn()
}))

vi.mock('@/themes/user-themes', () => ({
  $marketplaceInstalls: {
    get: () => new Map(),
    listen: () => () => {},
    subscribe: (callback: (value: Map<string, unknown>) => void) => {
      callback(new Map())

      return () => {}
    }
  },
  isUserTheme: () => false,
  removeUserTheme: vi.fn()
}))

vi.mock('./pet-settings', () => ({
  PetSettings: () => <div>Pet settings</div>
}))

beforeEach(() => {
  setMenuBarCommandReferenceEnabled.mockResolvedValue({ enabled: false })
  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true,
    value: {
      settings: {
        getMenuBarCommandReferenceEnabled: vi.fn().mockResolvedValue({ enabled: true }),
        setMenuBarCommandReferenceEnabled
      }
    }
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true,
    value: undefined
  })
})

describe('AppearanceSettings', () => {
  it('renders a menu bar command switch between inline embeds and pet settings', async () => {
    const { AppearanceSettings } = await import('./appearance-settings')
    const queryClient = new QueryClient()

    render(
      <QueryClientProvider client={queryClient}>
        <AppearanceSettings />
      </QueryClientProvider>
    )

    const switchEl = await screen.findByRole('switch', { name: 'Menu Bar Commands' })
    const text = document.body.textContent ?? ''

    expect(text.indexOf('Inline Embeds')).toBeLessThan(text.indexOf('Menu Bar Commands'))
    expect(text.indexOf('Menu Bar Commands')).toBeLessThan(text.indexOf('Pet settings'))

    fireEvent.click(switchEl)

    await waitFor(() => expect(setMenuBarCommandReferenceEnabled).toHaveBeenCalledWith(false))
  })
})
