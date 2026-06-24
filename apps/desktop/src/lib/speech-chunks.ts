export interface SpeechChunkOptions {
  maxChars?: number
  minChars?: number
}

const DEFAULT_MAX_CHARS = 320
const DEFAULT_MIN_CHARS = 8
const SENTENCE_END_RE = /[.!?。！？](?=\s|$)/g
const SOFT_BOUNDARIES = [', ', '; ', ': ', ' — ', ' – ']

function firstSentenceEnd(text: string): number | null {
  SENTENCE_END_RE.lastIndex = 0
  const match = SENTENCE_END_RE.exec(text)

  return match ? match.index + match[0].length : null
}

function findSoftBoundary(text: string, maxChars: number): number {
  const search = text.slice(0, maxChars)
  let boundary = -1
  let boundaryLength = 0

  for (const token of SOFT_BOUNDARIES) {
    const index = search.lastIndexOf(token)

    if (index > boundary) {
      boundary = index
      boundaryLength = token.length
    }
  }

  if (boundary > 0) {
    return boundary + boundaryLength
  }

  const whitespace = search.lastIndexOf(' ')

  if (whitespace > 0) {
    return whitespace + 1
  }

  return maxChars
}

export function splitSpeechText(text: string, options: SpeechChunkOptions = {}): string[] {
  const maxChars = Math.max(40, options.maxChars ?? DEFAULT_MAX_CHARS)
  const minChars = Math.max(1, options.minChars ?? DEFAULT_MIN_CHARS)
  const chunks: string[] = []
  let remaining = text.replace(/\s+/g, ' ').trim()

  while (remaining) {
    const sentenceEnd = firstSentenceEnd(remaining)

    if (remaining.length <= maxChars && (!sentenceEnd || sentenceEnd === remaining.length)) {
      chunks.push(remaining)

      break
    }

    let end = 0

    if (sentenceEnd && sentenceEnd >= minChars && sentenceEnd <= maxChars) {
      end = sentenceEnd
    } else {
      end = findSoftBoundary(remaining, maxChars)
    }

    const chunk = remaining.slice(0, end).trim()

    if (chunk) {
      chunks.push(chunk)
    }

    remaining = remaining.slice(Math.max(end, 1)).trim()
  }

  return chunks
}
