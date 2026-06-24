import { describe, expect, it } from 'vitest'

import { splitSpeechText } from './speech-chunks'

describe('splitSpeechText', () => {
  it('uses sentence boundaries for short read-aloud chunks', () => {
    expect(splitSpeechText('First sentence. Second sentence! Third sentence?')).toEqual([
      'First sentence.',
      'Second sentence!',
      'Third sentence?'
    ])
  })

  it('falls back to soft boundaries when a sentence is too long', () => {
    const chunks = splitSpeechText(
      'This clause has enough words to cross the configured limit, and this comma gives it a safe place to split before the sentence finally ends.',
      { maxChars: 80 }
    )

    expect(chunks.length).toBeGreaterThan(1)
    expect(chunks.every(chunk => chunk.length <= 80)).toBe(true)
    expect(chunks.join(' ')).toBe(
      'This clause has enough words to cross the configured limit, and this comma gives it a safe place to split before the sentence finally ends.'
    )
  })
})
