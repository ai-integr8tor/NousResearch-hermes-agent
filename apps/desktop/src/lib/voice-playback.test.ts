import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { speakText } from '@/hermes'

import { playSpeechText, stopVoicePlayback } from './voice-playback'

vi.mock('@/hermes', () => ({
  speakText: vi.fn()
}))

interface FakeAudioListener {
  (): void
}

class FakeAudio {
  static instances: FakeAudio[] = []

  listeners = new Map<string, FakeAudioListener>()
  paused = false
  played = false
  src: string

  constructor(src: string) {
    this.src = src
    FakeAudio.instances.push(this)
  }

  addEventListener(event: string, listener: FakeAudioListener) {
    this.listeners.set(event, listener)
  }

  removeEventListener(event: string) {
    this.listeners.delete(event)
  }

  play() {
    this.played = true

    return Promise.resolve()
  }

  pause() {
    this.paused = true
  }

  load() {}

  finish() {
    this.listeners.get('ended')?.()
  }
}

const flush = () => new Promise(resolve => window.setTimeout(resolve, 0))

describe('playSpeechText', () => {
  beforeEach(() => {
    vi.stubGlobal('Audio', FakeAudio)
    FakeAudio.instances = []
    vi.mocked(speakText).mockReset()
  })

  afterEach(() => {
    stopVoicePlayback()
    vi.unstubAllGlobals()
  })

  it('starts synthesizing the next read-aloud chunk while the current chunk is playing', async () => {
    const resolvers: Array<() => void> = []
    vi.mocked(speakText).mockImplementation(
      text =>
        new Promise(resolve => {
          resolvers.push(() =>
            resolve({
              data_url: `data:audio/mpeg;base64,${window.btoa(text)}`,
              mime_type: 'audio/mpeg',
              ok: true,
              provider: 'test'
            })
          )
        })
    )

    const playback = playSpeechText('First sentence. Second sentence. Third sentence.', {
      messageId: 'm1',
      source: 'read-aloud'
    })

    expect(speakText).toHaveBeenCalledTimes(1)
    expect(speakText).toHaveBeenNthCalledWith(1, 'First sentence.')

    resolvers[0]()
    await flush()

    expect(FakeAudio.instances[0]?.played).toBe(true)
    expect(speakText).toHaveBeenCalledTimes(2)
    expect(speakText).toHaveBeenNthCalledWith(2, 'Second sentence.')

    resolvers[1]()
    FakeAudio.instances[0].finish()
    await flush()

    expect(FakeAudio.instances[1]?.played).toBe(true)
    expect(speakText).toHaveBeenCalledTimes(3)
    expect(speakText).toHaveBeenNthCalledWith(3, 'Third sentence.')

    resolvers[2]()
    FakeAudio.instances[1].finish()
    await flush()
    FakeAudio.instances[2].finish()

    await expect(playback).resolves.toBe(true)
  })

  it('suppresses prefetched synthesis errors after playback is stopped', async () => {
    let rejectSecondChunk: (error: Error) => void = (_error: Error) => {
      throw new Error('Second chunk rejecter was not captured')
    }

    vi.mocked(speakText).mockImplementation(text => {
      if (text === 'First sentence.') {
        return Promise.resolve({
          data_url: `data:audio/mpeg;base64,${window.btoa(text)}`,
          mime_type: 'audio/mpeg',
          ok: true,
          provider: 'test'
        })
      }

      return new Promise((_resolve, reject) => {
        rejectSecondChunk = reject
      })
    })

    const playback = playSpeechText('First sentence. Second sentence.', {
      messageId: 'm1',
      source: 'read-aloud'
    })

    await flush()

    expect(FakeAudio.instances[0]?.played).toBe(true)
    expect(speakText).toHaveBeenCalledTimes(2)

    FakeAudio.instances[0].finish()
    await flush()
    stopVoicePlayback()
    rejectSecondChunk(new Error('prefetched synthesis failed'))

    await expect(playback).resolves.toBe(false)
  })
})
