import { setModelPreset } from '@/store/model-presets'
import { notifyError } from '@/store/notifications'
import { setCurrentReasoningEffort } from '@/store/session'

/**
 * Shared write path for the composer's reasoning-effort pill and the per-row
 * reasoning submenu in the model picker. Writes the model's preset, optimistically
 * updates the active session's reasoning effort, and pushes the new value to the
 * gateway via `config.set`. On RPC failure reverts both the preset and the atom
 * to the user's pre-click value (`prev`) and notifies.
 *
 * Revert semantics: `prev` is captured at call time (before the optimistic write)
 * so a parallel session-info reply — which may overwrite the live atom — can't
 * poison the revert to the wrong value.
 *
 * Caveat (unresolved): rapid A→B clicks where A's RPC fails after B's optimistic
 * set has committed will still clobber B's value back to A's pre-click value. A
 * generation-counter guard would belong here, in one place.
 */
export async function applyReasoningPatch({
  failMessage,
  isActive,
  model,
  next,
  prev,
  provider,
  request,
  sessionId
}: {
  failMessage: string
  /**
   * Whether this write targets the user's currently-active model. The per-row
   * model picker submenu passes `false` for non-active rows (writes only the
   * preset, leaves the live session alone). The composer reasoning pill always
   * passes `true` (the composer pill only renders for the active model).
   */
  isActive: boolean
  model: string
  next: string
  prev: string
  provider: string
  /**
   * JSON-RPC function — accepts the same shape as `useGatewayRequest`'s
   * `requestGateway`. `null` skips the RPC (preset + optimistic store are
   * the whole effect); pass `null` only when no live session is reachable.
   */
  request: (<T>(method: string, params?: Record<string, unknown>) => Promise<T>) | null
  /** Live session id. Required when `isActive && request` is truthy. */
  sessionId: string | null
}): Promise<void> {
  setModelPreset(provider, model, { effort: next })

  if (!isActive) {
    return
  }

  setCurrentReasoningEffort(next)

  if (!sessionId || !request) {
    return
  }

  try {
    await request('config.set', { key: 'reasoning', session_id: sessionId, value: next })
  } catch (err) {
    setCurrentReasoningEffort(prev)
    setModelPreset(provider, model, { effort: prev })
    notifyError(err, failMessage)
  }
}
