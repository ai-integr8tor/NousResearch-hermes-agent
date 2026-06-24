/**
 * Resolve the rebuilt macOS `.app` bundle produced by the in-app update's
 * `hermes desktop --build-only` step, so the swap/relaunch can install it.
 *
 * electron-builder writes the bundle under a platform/arch-specific directory:
 *   - `release/mac-arm64/Hermes.app`  (Apple Silicon)
 *   - `release/mac-x64/Hermes.app`    (Intel, when the build pins the arch)
 *   - `release/mac/Hermes.app`        (host-arch default, no explicit arch)
 *
 * The updater historically only checked `mac-arm64` and `mac`, so an Intel
 * rebuild landing in `release/mac-x64` was missed: the swap/relaunch found no
 * bundle and the update silently degraded to "Restart Hermes to load the new
 * version" instead of installing the rebuilt app (issue #48160).
 *
 * Resolve the running process's arch first — the same assumption the desktop
 * build/validation path makes (apps/desktop/scripts/test-desktop.mjs maps
 * arm64 -> mac-arm64, else mac-x64; the hermes_cli `_desktop_packaged_executable`
 * helper globs `mac*`) — then fall back to the generic `mac` dir. Preferring the
 * host arch also stops an Intel host from selecting a stale `mac-arm64` bundle.
 * A non-x64/non-arm64 `process.arch` falls back to `release/mac` only rather
 * than guessing an arch-specific dir.
 *
 * Run with: node --test electron/mac-rebuilt-app.test.cjs
 * (Wired into npm test:desktop:platforms in package.json.)
 */

const fs = require('node:fs')
const path = require('node:path')

function directoryExists(p) {
  try {
    return fs.statSync(p).isDirectory()
  } catch {
    return false
  }
}

/**
 * @param {string} updateRoot install root being updated (holds apps/desktop/release)
 * @param {{ arch?: string, exists?: (p: string) => boolean }} [opts]
 *   `arch` defaults to process.arch; `exists` defaults to a real fs probe.
 *   Both are injectable so the resolution is unit-testable without a real tree.
 * @returns {string | undefined} absolute path to the rebuilt Hermes.app, or
 *   undefined when no bundle exists.
 */
function resolveRebuiltMacApp(updateRoot, { arch = process.arch, exists = directoryExists } = {}) {
  const releaseDir = path.join(updateRoot, 'apps', 'desktop', 'release')
  const archDir = arch === 'arm64' ? 'mac-arm64' : arch === 'x64' ? 'mac-x64' : null
  return [archDir, 'mac']
    .filter(Boolean)
    .map(dir => path.join(releaseDir, dir, 'Hermes.app'))
    .find(exists)
}

module.exports = { resolveRebuiltMacApp }
