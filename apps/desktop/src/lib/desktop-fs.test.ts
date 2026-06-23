import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { $connection } from '@/store/session'

import {
  desktopDefaultCwd,
  desktopGitRoot,
  desktopFsCacheKey,
  readDesktopDir,
  readDesktopFileDataUrl,
  readDesktopFileText,
  selectDesktopPaths,
  setDesktopFsRemotePicker
} from './desktop-fs'

const readDir = vi.fn(async () => ({ entries: [{ name: 'local', path: '/local', isDirectory: true }] }))
const readFileText = vi.fn(async () => ({ path: '/local/file.txt', text: 'local', byteSize: 5 }))
const readFileDataUrl = vi.fn(async () => 'data:text/plain;base64,bG9jYWw=')
const gitRoot = vi.fn(async () => '/local')
const selectPaths = vi.fn(async () => ['/local'])
const api = vi.fn(async ({ path }: { path: string }) => {
  if (path.startsWith('/api/fs/list?')) return { entries: [{ name: 'remote', path: '/remote', isDirectory: true }] }
  if (path.startsWith('/api/fs/read-text?')) return { path: '/remote/file.txt', text: 'remote', byteSize: 6 }
  if (path.startsWith('/api/fs/read-data-url?')) return { dataUrl: 'data:text/plain;base64,cmVtb3Rl' }
  if (path.startsWith('/api/fs/git-root?')) return { root: '/remote' }
  if (path === '/api/fs/default-cwd') return { cwd: '/backend/project', branch: 'main' }
  throw new Error(`unexpected path ${path}`)
})

function stubBridge() {
  vi.stubGlobal('window', {
    hermesDesktop: {
      api,
      gitRoot,
      readDir,
      readFileDataUrl,
      readFileText,
      selectPaths
    }
  })
}

describe('desktop filesystem facade', () => {
  beforeEach(() => {
    stubBridge()
    $connection.set(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    $connection.set(null)
    setDesktopFsRemotePicker(null)
  })

  it('uses local Electron filesystem methods in local mode', async () => {
    $connection.set({ mode: 'local' } as never)

    await expect(readDesktopDir('/work')).resolves.toEqual({ entries: [{ name: 'local', path: '/local', isDirectory: true }] })
    await expect(readDesktopFileText('/work/file.txt')).resolves.toMatchObject({ text: 'local' })
    await expect(readDesktopFileDataUrl('/work/file.txt')).resolves.toBe('data:text/plain;base64,bG9jYWw=')
    await expect(desktopGitRoot('/work')).resolves.toBe('/local')
    await expect(selectDesktopPaths({ directories: true })).resolves.toEqual(['/local'])

    expect(readDir).toHaveBeenCalledWith('/work')
    expect(readFileText).toHaveBeenCalledWith('/work/file.txt')
    expect(readFileDataUrl).toHaveBeenCalledWith('/work/file.txt')
    expect(gitRoot).toHaveBeenCalledWith('/work')
    expect(selectPaths).toHaveBeenCalledWith({ directories: true })
    expect(api).not.toHaveBeenCalled()
  })

  it('routes filesystem reads through authenticated backend REST in remote mode', async () => {
    $connection.set({ mode: 'remote' } as never)

    await expect(readDesktopDir('/home/user/project')).resolves.toMatchObject({ entries: [{ name: 'remote' }] })
    await expect(readDesktopFileText('/home/user/project/a b.txt')).resolves.toMatchObject({ text: 'remote' })
    await expect(readDesktopFileDataUrl('/home/user/project/a b.txt')).resolves.toBe('data:text/plain;base64,cmVtb3Rl')
    await expect(desktopGitRoot('/home/user/project')).resolves.toBe('/remote')
    await expect(desktopDefaultCwd()).resolves.toEqual({ cwd: '/backend/project', branch: 'main' })

    expect(api).toHaveBeenCalledWith({ path: '/api/fs/list?path=%2Fhome%2Fuser%2Fproject' })
    expect(api).toHaveBeenCalledWith({ path: '/api/fs/read-text?path=%2Fhome%2Fuser%2Fproject%2Fa%20b.txt' })
    expect(api).toHaveBeenCalledWith({ path: '/api/fs/read-data-url?path=%2Fhome%2Fuser%2Fproject%2Fa%20b.txt' })
    expect(api).toHaveBeenCalledWith({ path: '/api/fs/git-root?path=%2Fhome%2Fuser%2Fproject' })
    expect(api).toHaveBeenCalledWith({ path: '/api/fs/default-cwd' })
    expect(readDir).not.toHaveBeenCalled()
    expect(readFileText).not.toHaveBeenCalled()
    expect(readFileDataUrl).not.toHaveBeenCalled()
    expect(gitRoot).not.toHaveBeenCalled()
  })

  it('uses the registered in-app directory picker in remote mode', async () => {
    const remoteSelect = vi.fn(async () => ['/remote/project'])
    $connection.set({ mode: 'remote' } as never)
    setDesktopFsRemotePicker({ selectPaths: remoteSelect })

    await expect(selectDesktopPaths({ defaultPath: '/remote', directories: true, multiple: false })).resolves.toEqual([
      '/remote/project'
    ])

    expect(remoteSelect).toHaveBeenCalledWith({ defaultPath: '/remote', directories: true, multiple: false })
    expect(selectPaths).not.toHaveBeenCalled()
  })

  it('does not treat the remote directory picker as a general file picker', async () => {
    const remoteSelect = vi.fn(async () => ['/remote/project'])
    $connection.set({ mode: 'remote' } as never)
    setDesktopFsRemotePicker({ selectPaths: remoteSelect })

    await expect(selectDesktopPaths({ directories: false, multiple: false })).resolves.toEqual([])
    await expect(selectDesktopPaths({ directories: true, multiple: true })).resolves.toEqual([])

    expect(remoteSelect).not.toHaveBeenCalled()
    expect(selectPaths).not.toHaveBeenCalled()
  })

  it('cache key distinguishes two SSH hosts that share the same local forwarded port', () => {
    // Both remotes resolve to the same loopback tunnel baseUrl (the local
    // forwarded port is reusable across remotes). Without the remoteHost in the
    // identity these collide and one host's cached fs reads serve the other.
    $connection.set({ mode: 'remote', baseUrl: 'http://127.0.0.1:50001', remoteHost: 'jonny@mac-mini' } as never)
    const keyA = desktopFsCacheKey()
    $connection.set({ mode: 'remote', baseUrl: 'http://127.0.0.1:50001', remoteHost: 'jonny@ubuntu-box' } as never)
    const keyB = desktopFsCacheKey()

    expect(keyA).not.toBe(keyB)
    expect(keyA).toContain('mac-mini')
    expect(keyB).toContain('ubuntu-box')
  })

  it('cache key falls back to baseUrl when no remoteHost is present', () => {
    $connection.set({ mode: 'remote', baseUrl: 'https://box.tail1234.ts.net' } as never)
    expect(desktopFsCacheKey()).toContain('box.tail1234.ts.net')
    $connection.set(null)
    expect(desktopFsCacheKey()).toBe('local:')
  })
})
