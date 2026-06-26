// Pure timeline helpers — no React/DOM; tested in thread-timeline-data.test.ts.

export interface TimelineSourceMessage {
  id: string
  role: string
  text: string
}

export interface TimelineEntry {
  id: string
  preview: string
}

// Injected as user messages for alternation; not human prompts (thread.tsx).
const PROCESS_NOTIFICATION_RE = /^\[IMPORTANT: Background process [\s\S]*\]$/

const PREVIEW_MAX = 120

export function timelinePreview(text: string, max: number = PREVIEW_MAX): string {
  const collapsed = text.replace(/\s+/g, ' ').trim()

  if (collapsed.length <= max) {
    return collapsed
  }

  return `${collapsed.slice(0, max - 1).trimEnd()}…`
}

export function deriveTimelineEntries(messages: readonly TimelineSourceMessage[]): TimelineEntry[] {
  const entries: TimelineEntry[] = []

  for (const message of messages) {
    if (message.role !== 'user') {
      continue
    }

    const text = message.text.trim()

    if (!text || PROCESS_NOTIFICATION_RE.test(text)) {
      continue
    }

    entries.push({ id: message.id, preview: timelinePreview(text) })
  }

  return entries
}

/** Last user prompt at/above the viewport top (with slack); else first rendered. */
export function activeTimelineIndex(offsets: readonly (number | null)[], slack: number = 8): number {
  let active = -1
  let firstRendered = -1

  for (let i = 0; i < offsets.length; i++) {
    const offset = offsets[i]

    if (offset == null) {
      continue
    }

    if (firstRendered === -1) {
      firstRendered = i
    }

    if (offset <= slack) {
      active = i
    }
  }

  if (active !== -1) {
    return active
  }

  return firstRendered === -1 ? 0 : firstRendered
}

/**
 * Map a user-message id to its `groups` index (the i-th user message in the
 * session, after ThreadMessageList's budget walk packs each user with its
 * assistant turns). Returns -1 when the id isn't a user message.
 *
 * The current click handler (`jumpToPrompt` in thread-timeline.tsx) uses
 * `entries.findIndex` against the already-derived entries array instead, so
 * this helper has no production caller at the moment — but it's retained as
 * a defensive export for future timeline controls that may operate on raw
 * message arrays, and the tests below lock in the colon-in-id contract so
 * future callers don't accidentally reintroduce the joined-serialization
 * round-trip the timeline used to do (issue #52816).
 */
export function userMessageIndex(messages: readonly { id: string; role: string }[], targetId: string): number {
  let userIndex = 0

  for (const message of messages) {
    if (message.role === 'user') {
      if (message.id === targetId) {
        return userIndex
      }

      userIndex += 1
    }
  }

  return -1
}
