type FrameCallback = () => void
type FrameHandle = ReturnType<typeof setTimeout> | number

interface FrameScheduler {
  cancelFrame: (handle: FrameHandle) => void
  requestFrame: (callback: FrameCallback) => FrameHandle
}

interface RunStartAnchorOptions extends Partial<FrameScheduler> {
  scrollToBottom: (behavior?: 'instant') => boolean | Promise<boolean>
  stopScroll: () => void
}

const defaultRequestFrame = (callback: FrameCallback): FrameHandle => {
  if (typeof globalThis.requestAnimationFrame === 'function') {
    return globalThis.requestAnimationFrame(() => callback())
  }

  return setTimeout(callback, 0)
}

const defaultCancelFrame = (handle: FrameHandle) => {
  if (typeof globalThis.cancelAnimationFrame === 'function' && typeof handle === 'number') {
    globalThis.cancelAnimationFrame(handle)

    return
  }

  clearTimeout(handle)
}

export function createRunStartAnchor({
  cancelFrame = defaultCancelFrame,
  requestFrame = defaultRequestFrame,
  scrollToBottom,
  stopScroll
}: RunStartAnchorOptions) {
  let pendingFrame: FrameHandle | null = null

  const cancel = () => {
    if (pendingFrame !== null) {
      cancelFrame(pendingFrame)
      pendingFrame = null
    }
  }

  const anchor = () => {
    cancel()

    pendingFrame = requestFrame(() => {
      pendingFrame = null
      void scrollToBottom('instant')
      stopScroll()
    })
  }

  return { anchor, cancel }
}
