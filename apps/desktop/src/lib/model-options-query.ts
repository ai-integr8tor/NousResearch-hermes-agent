export type ModelOptionsQueryScope = 'configured' | 'all'

export const MODEL_OPTIONS_QUERY_ROOT = ['model-options'] as const

export function modelOptionsQueryKey(scope: ModelOptionsQueryScope, sessionId?: string | null) {
  return [...MODEL_OPTIONS_QUERY_ROOT, scope, sessionId || 'global'] as const
}
