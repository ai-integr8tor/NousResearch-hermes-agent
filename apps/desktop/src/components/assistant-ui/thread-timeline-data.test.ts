import { describe, expect, it } from 'vitest'

import { activeTimelineIndex, deriveTimelineEntries, timelinePreview, userMessageIndex } from './thread-timeline-data'

describe('timelinePreview', () => {
  it('collapses whitespace to a single line', () => {
    expect(timelinePreview('hello\n\n  world\tagain')).toBe('hello world again')
  })

  it('truncates with an ellipsis past the limit', () => {
    const out = timelinePreview('abcdefghij', 5)
    expect(out).toBe('abcd…')
    expect(out.length).toBe(5)
  })
})

describe('deriveTimelineEntries', () => {
  it('keeps non-empty user prompts in order', () => {
    expect(
      deriveTimelineEntries([
        { id: 'u1', role: 'user', text: 'first' },
        { id: 'a1', role: 'assistant', text: 'answer' },
        { id: 'u2', role: 'user', text: '  second  ' }
      ])
    ).toEqual([
      { id: 'u1', preview: 'first' },
      { id: 'u2', preview: 'second' }
    ])
  })

  it('drops blanks and background-process notifications', () => {
    expect(
      deriveTimelineEntries([
        { id: 'u1', role: 'user', text: '   ' },
        { id: 'u2', role: 'user', text: '[IMPORTANT: Background process 123 finished]' },
        { id: 'u3', role: 'user', text: 'real prompt' }
      ]).map(e => e.id)
    ).toEqual(['u3'])
  })
})

describe('activeTimelineIndex', () => {
  it('returns the last prompt scrolled to or above the top edge', () => {
    expect(activeTimelineIndex([-400, -10, 320])).toBe(1)
  })

  it('falls back to the first rendered entry', () => {
    expect(activeTimelineIndex([null, 120, 480])).toBe(1)
    expect(activeTimelineIndex([null, null])).toBe(0)
  })
})

describe('userMessageIndex', () => {
  it('counts user messages until the target id is found', () => {
    expect(
      userMessageIndex(
        [
          { id: 'u1', role: 'user' },
          { id: 'a1', role: 'assistant' },
          { id: 'u2', role: 'user' },
          { id: 'u3', role: 'user' }
        ],
        'u3'
      )
    ).toBe(2)
  })

  it('returns the first user ordinal for the leading user message', () => {
    expect(
      userMessageIndex(
        [
          { id: 'u1', role: 'user' },
          { id: 'a1', role: 'assistant' }
        ],
        'u1'
      )
    ).toBe(0)
  })

  it('returns -1 when the id is not a user message', () => {
    expect(
      userMessageIndex(
        [
          { id: 'u1', role: 'user' },
          { id: 'a1', role: 'assistant' }
        ],
        'a1'
      )
    ).toBe(-1)
  })

  it('returns -1 when the id is missing entirely', () => {
    expect(
      userMessageIndex(
        [
          { id: 'u1', role: 'user' }
        ],
        'unknown'
      )
    ).toBe(-1)
  })
})
