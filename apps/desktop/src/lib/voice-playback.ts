import { speakText } from '@/hermes'
import {
  $voicePlayback,
  setVoicePlaybackState,
  type VoicePlaybackSource,
  type VoicePlaybackState
} from '@/store/voice-playback'

import { splitSpeechText } from './speech-chunks'
import { sanitizeTextForSpeech } from './speech-text'

let currentAudio: HTMLAudioElement | null = null
let currentStop: (() => void) | null = null
let sequence = 0

function currentState(
  status: VoicePlaybackState['status'],
  options?: VoicePlaybackOptions,
  audioElement: HTMLAudioElement | null = null
): VoicePlaybackState {
  return {
    audioElement,
    messageId: options?.messageId ?? null,
    sequence,
    source: options?.source ?? null,
    status
  }
}

function waitForAudio(audio: HTMLAudioElement): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const cleanup = () => {
      audio.removeEventListener('ended', onEnded)
      audio.removeEventListener('error', onError)
      currentStop = null
    }

    const onEnded = () => {
      cleanup()
      resolve()
    }

    const onError = () => {
      cleanup()
      reject(new Error('Playback failed'))
    }

    currentStop = () => {
      cleanup()
      resolve()
    }

    audio.addEventListener('ended', onEnded, { once: true })
    audio.addEventListener('error', onError, { once: true })
    void audio.play().catch(reject)
  })
}

export interface VoicePlaybackOptions {
  messageId?: string | null
  source: VoicePlaybackSource
}

export function stopVoicePlayback() {
  sequence += 1
  currentStop?.()
  currentStop = null

  if (currentAudio) {
    currentAudio.pause()
    currentAudio.src = ''
    currentAudio.load()
    currentAudio = null
  }

  setVoicePlaybackState({
    audioElement: null,
    messageId: null,
    sequence,
    source: null,
    status: 'idle'
  })
}

export async function playSpeechText(text: string, options: VoicePlaybackOptions): Promise<boolean> {
  stopVoicePlayback()

  const speakableText = sanitizeTextForSpeech(text)

  if (!speakableText) {
    return false
  }

  const chunks = splitSpeechText(speakableText)

  if (!chunks.length) {
    return false
  }

  const ownSequence = sequence
  const isCurrent = () => ownSequence === sequence
  const prepared = new Map<number, ReturnType<typeof speakText>>()

  const prepareChunk = (index: number) => {
    const chunk = chunks[index]

    if (!chunk) {
      return null
    }

    let request = prepared.get(index)

    if (!request) {
      request = speakText(chunk)
      // If playback is stopped before this prefetched request is awaited, keep
      // the browser from reporting an unhandled rejection. Awaiting the stored
      // promise still observes and propagates the original error.
      void request.catch(() => undefined)
      prepared.set(index, request)
    }

    return request
  }

  setVoicePlaybackState(currentState('preparing', options))

  try {
    prepareChunk(0)

    for (let index = 0; index < chunks.length; index += 1) {
      const responseRequest = prepareChunk(index)

      if (!responseRequest) {
        continue
      }

      const response = await responseRequest

      if (!isCurrent()) {
        return false
      }

      const audio = new Audio(response.data_url)
      currentAudio = audio
      setVoicePlaybackState(currentState('speaking', options, audio))

      prepareChunk(index + 1)

      await waitForAudio(audio)

      if (!isCurrent()) {
        return false
      }

      if (currentAudio === audio) {
        currentAudio = null
      }
    }

    setVoicePlaybackState(currentState('idle'))

    return true
  } catch (error) {
    if (!isCurrent()) {
      return false
    }

    currentStop = null
    currentAudio = null
    setVoicePlaybackState(currentState('idle'))

    throw error
  }
}

export function isVoicePlaybackActive() {
  return $voicePlayback.get().status !== 'idle'
}
