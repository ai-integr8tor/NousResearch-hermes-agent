import { describe, expect, it } from 'vitest'

import {
  currentPickerSelection,
  displayModelName,
  formatModelPillLabel,
  formatReasoningPillLabel,
  isThinkingEnabled,
  normalizeReasoningEffort,
  REASONING_EFFORT_OPTIONS,
  reasoningEffortLabel
} from './model-status-label'

describe('model-status-label', () => {
  it('formats display names consistently', () => {
    expect(displayModelName('anthropic/claude-opus-4.8-fast')).toBe('Opus 4.8')
    expect(displayModelName('openai/gpt-5.5-fast')).toBe('GPT-5.5')
    expect(displayModelName('deepseek/deepseek-v4-pro-thinking')).toBe('Deepseek V4 Pro')
    expect(displayModelName('openai/gpt-5.5')).toBe('GPT-5.5')
  })

  it('strips trailing date-pin snapshots from the display name', () => {
    expect(displayModelName('claude-opus-4-5-20251101')).toBe('Opus 4 5')
    expect(displayModelName('anthropic/claude-haiku-4-5-20251001')).toBe('Haiku 4 5')
  })

  it('maps reasoning effort to compact labels', () => {
    expect(reasoningEffortLabel('high')).toBe('High')
    expect(reasoningEffortLabel('xhigh')).toBe('Max')
    expect(reasoningEffortLabel('')).toBe('')
  })

  it('exposes the full effort options list for the picker radio group', () => {
    expect(REASONING_EFFORT_OPTIONS.map(option => option.value)).toEqual([
      'minimal',
      'low',
      'medium',
      'high',
      'xhigh'
    ])
  })

  it('treats empty effort as thinking-on (Hermes default) and only none as off', () => {
    expect(isThinkingEnabled('')).toBe(true)
    expect(isThinkingEnabled('medium')).toBe(true)
    expect(isThinkingEnabled('none')).toBe(false)
  })

  it('normalizes effort to a valid radio value, with "none" → "" and unknown → medium', () => {
    expect(normalizeReasoningEffort('high')).toBe('high')
    expect(normalizeReasoningEffort('none')).toBe('')
    expect(normalizeReasoningEffort('gibberish')).toBe('medium')
    expect(normalizeReasoningEffort('')).toBe('medium')
  })

  it('formats the model pill as just the name (no effort suffix)', () => {
    expect(formatModelPillLabel('openai/gpt-5.5', { fastMode: true })).toBe('GPT-5.5 · Fast')
    expect(formatModelPillLabel('openai/gpt-5.5')).toBe('GPT-5.5')
  })

  it('appends · Fast to the model pill when the active variant is a `-fast` sibling', () => {
    expect(formatModelPillLabel('openai/gpt-5.5-fast')).toBe('GPT-5.5 · Fast')
  })

  it('returns just the placeholder name when the model is empty', () => {
    expect(formatModelPillLabel('')).toBe('No model')
    expect(formatModelPillLabel('   ')).toBe('No model')
  })

  it('formats the reasoning pill label, falling back to Med for empty effort', () => {
    expect(formatReasoningPillLabel('high')).toBe('High')
    expect(formatReasoningPillLabel('xhigh')).toBe('Max')
    expect(formatReasoningPillLabel('none')).toBe('Off')
    expect(formatReasoningPillLabel('')).toBe('Med')
  })

  describe('currentPickerSelection', () => {
    const store = { model: 'opus', provider: 'anthropic' }
    const options = { model: 'hermes-4', provider: 'nous' }

    it('prefers the sticky composer pick over the profile default pre-session', () => {
      expect(currentPickerSelection(false, store, options)).toEqual(store)
    })

    it('lets the live session model.options win when a session exists', () => {
      expect(currentPickerSelection(true, store, options)).toEqual(options)
    })

    it('falls back to options when the store is empty', () => {
      expect(currentPickerSelection(false, { model: '', provider: '' }, options)).toEqual(options)
    })

    it('falls back to the store while options are still loading', () => {
      expect(currentPickerSelection(true, store, undefined)).toEqual(store)
    })
  })
})
