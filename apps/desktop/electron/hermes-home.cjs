const os = require('node:os')
const path = require('node:path')
const { normalizeHermesHomeRoot } = require('./backend-env.cjs')
const { readWindowsUserEnvVar } = require('./windows-user-env.cjs')

function windowsDefaultHermesHome({
  env = process.env,
  homeDir = os.homedir(),
  pathModule = path.win32
} = {}) {
  const localAppData = String(env.LOCALAPPDATA || '').trim()
  const base = localAppData || pathModule.join(homeDir, 'AppData', 'Local')
  return pathModule.join(base, 'hermes')
}

function resolveHermesHome({
  env = process.env,
  userDataOverride = env.HERMES_DESKTOP_USER_DATA_DIR,
  isWindows = process.platform === 'win32',
  homeDir = os.homedir(),
  directoryExists = () => false,
  readUserEnvVar = readWindowsUserEnvVar,
  pathModule = isWindows ? path.win32 : path.posix,
  normalizeRoot = normalizeHermesHomeRoot
} = {}) {
  if (env.HERMES_HOME) return normalizeRoot(env.HERMES_HOME, { pathModule })
  if (userDataOverride) return pathModule.join(pathModule.resolve(userDataOverride), 'hermes-home')
  if (isWindows) {
    const fromRegistry = readUserEnvVar('HERMES_HOME')
    if (fromRegistry) return normalizeRoot(fromRegistry, { pathModule })

    const localappdata = windowsDefaultHermesHome({ env, homeDir, pathModule })
    const legacy = pathModule.join(homeDir, '.hermes')
    // Migrate transparently to LOCALAPPDATA, but honour an existing legacy
    // ~/.hermes setup (no LOCALAPPDATA install yet) so users don't lose state.
    if (!directoryExists(localappdata) && directoryExists(legacy)) return legacy
    return localappdata
  }
  return pathModule.join(homeDir, '.hermes')
}

module.exports = {
  resolveHermesHome,
  windowsDefaultHermesHome
}
