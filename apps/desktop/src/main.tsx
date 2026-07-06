import './styles.css'
// Side-effect: applies the persisted window translucency on load.
import './store/translucency'

import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'

import App from './app'
import { ErrorBoundary } from './components/error-boundary'
import { HapticsProvider } from './components/haptics-provider'
import { I18nProvider } from './i18n'
import { installClipboardShim } from './lib/clipboard'
import { queryClient } from './lib/query-client'
import { ThemeProvider } from './themes/context'

installClipboardShim()

// Dev-only: install __PERF_DRIVE__ + __PERF_PROBE__ on window so the
// scripts/ harnesses can drive a synthetic stream + record render cost.
// Tree-shaken out of production builds. (Uses MODE rather than DEV because
// our Vite setup currently bundles with PROD=true even in `vite dev`; see
// scripts/dev-no-hmr.mjs for the surrounding workarounds.)
if (import.meta.env.MODE !== 'production') {
  import('./app/chat/perf-probe')
}

const windowKind = new URLSearchParams(window.location.search).get('win')

document.documentElement.dataset.windowKind = windowKind ?? 'app'
document.body.dataset.windowKind = windowKind ?? 'app'

if (windowKind === 'slash-reference') {
  document.documentElement.style.backgroundColor = 'transparent'
  document.body.style.backgroundColor = 'transparent'
}

// Helper windows ride this same bundle but mount small, gateway-less surfaces
// instead of the full app. Branch before app-shell work so they stay cheap.
if (windowKind === 'overlay') {
  void import('./app/pet-overlay/overlay-root').then(({ mountPetOverlay }) => mountPetOverlay())
} else if (windowKind === 'slash-reference') {
  void import('./app/slash-reference/slash-reference-app').then(({ SlashReferenceApp }) => {
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        <ErrorBoundary label="slash-reference-root">
          <ThemeProvider>
            <SlashReferenceApp />
          </ThemeProvider>
        </ErrorBoundary>
      </StrictMode>
    )
  })
} else {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ErrorBoundary label="root">
        <QueryClientProvider client={queryClient}>
          <I18nProvider>
            <ThemeProvider>
              <HapticsProvider>
                <HashRouter>
                  <App />
                </HashRouter>
              </HapticsProvider>
            </ThemeProvider>
          </I18nProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </StrictMode>
  )
}
