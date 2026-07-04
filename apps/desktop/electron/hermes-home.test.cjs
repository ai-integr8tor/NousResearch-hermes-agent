const assert = require('node:assert/strict')
const { test } = require('node:test')
const path = require('node:path')

const { resolveHermesHome, windowsDefaultHermesHome } = require('./hermes-home.cjs')

function resolverOptions(options = {}) {
  const existing = new Set(options.existing || [])
  return {
    homeDir: 'C:\\Users\\ada',
    isWindows: true,
    pathModule: path.win32,
    readUserEnvVar: () => null,
    directoryExists: p => existing.has(p),
    ...options
  }
}

test('Windows default Hermes home uses LOCALAPPDATA when present', () => {
  assert.equal(
    windowsDefaultHermesHome({
      env: { LOCALAPPDATA: 'C:\\Users\\ada\\AppData\\Local' },
      homeDir: 'C:\\Users\\ada',
      pathModule: path.win32
    }),
    'C:\\Users\\ada\\AppData\\Local\\hermes'
  )
})

test('Windows default Hermes home falls back to AppData\\Local when LOCALAPPDATA is absent', () => {
  assert.equal(
    windowsDefaultHermesHome({
      env: {},
      homeDir: 'C:\\Users\\ada',
      pathModule: path.win32
    }),
    'C:\\Users\\ada\\AppData\\Local\\hermes'
  )
})

test('resolveHermesHome honors explicit HERMES_HOME before defaults', () => {
  assert.equal(
    resolveHermesHome(
      resolverOptions({
        env: { HERMES_HOME: 'D:\\Hermes\\profiles\\work' }
      })
    ),
    'D:\\Hermes'
  )
})

test('resolveHermesHome reads the live Windows user environment before defaults', () => {
  assert.equal(
    resolveHermesHome(
      resolverOptions({
        env: { LOCALAPPDATA: 'C:\\Users\\ada\\AppData\\Local' },
        readUserEnvVar: name => (name === 'HERMES_HOME' ? 'E:\\Hermes' : null)
      })
    ),
    'E:\\Hermes'
  )
})

test('resolveHermesHome keeps an existing legacy Windows .hermes when no local appdata install exists', () => {
  assert.equal(
    resolveHermesHome(
      resolverOptions({
        env: { LOCALAPPDATA: 'C:\\Users\\ada\\AppData\\Local' },
        existing: ['C:\\Users\\ada\\.hermes']
      })
    ),
    'C:\\Users\\ada\\.hermes'
  )
})

test('resolveHermesHome aligns Windows fallback with Python when LOCALAPPDATA is missing', () => {
  assert.equal(
    resolveHermesHome(
      resolverOptions({
        env: {}
      })
    ),
    'C:\\Users\\ada\\AppData\\Local\\hermes'
  )
})

test('resolveHermesHome uses ~/.hermes on non-Windows platforms', () => {
  assert.equal(
    resolveHermesHome({
      env: {},
      homeDir: '/Users/ada',
      isWindows: false,
      pathModule: path.posix
    }),
    '/Users/ada/.hermes'
  )
})
