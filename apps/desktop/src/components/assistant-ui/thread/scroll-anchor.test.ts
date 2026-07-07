import { describe, expect, it, vi } from 'vitest'

import { createRunStartAnchor } from './scroll-anchor'

describe('createRunStartAnchor', () => {
  it('anchors the new assistant turn once, then releases sticky resize-follow', () => {
    const callbacks: Array<() => void> = []
    const scrollToBottom = vi.fn()
    const stopScroll = vi.fn()

    const anchor = createRunStartAnchor({
      cancelFrame: vi.fn(),
      requestFrame: callback => {
        callbacks.push(callback)

        return callbacks.length
      },
      scrollToBottom,
      stopScroll
    })

    anchor.anchor()

    expect(scrollToBottom).not.toHaveBeenCalled()
    expect(stopScroll).not.toHaveBeenCalled()

    callbacks[0]()

    expect(scrollToBottom).toHaveBeenCalledTimes(1)
    expect(scrollToBottom).toHaveBeenCalledWith('instant')
    expect(stopScroll).toHaveBeenCalledTimes(1)
    expect(stopScroll.mock.invocationCallOrder[0]).toBeGreaterThan(
      scrollToBottom.mock.invocationCallOrder[0]
    )
  })

  it('coalesces repeated run-start events to the latest frame', () => {
    const callbacks: Array<() => void> = []
    const cancelFrame = vi.fn()
    const anchor = createRunStartAnchor({
      cancelFrame,
      requestFrame: callback => {
        callbacks.push(callback)

        return callbacks.length
      },
      scrollToBottom: vi.fn(),
      stopScroll: vi.fn()
    })

    anchor.anchor()
    anchor.anchor()

    expect(cancelFrame).toHaveBeenCalledTimes(1)
    expect(cancelFrame).toHaveBeenCalledWith(1)
  })

  it('cancels a pending frame on cleanup', () => {
    const cancelFrame = vi.fn()
    const anchor = createRunStartAnchor({
      cancelFrame,
      requestFrame: () => 7,
      scrollToBottom: vi.fn(),
      stopScroll: vi.fn()
    })

    anchor.anchor()
    anchor.cancel()
    anchor.cancel()

    expect(cancelFrame).toHaveBeenCalledTimes(1)
    expect(cancelFrame).toHaveBeenCalledWith(7)
  })
})
