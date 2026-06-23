/**
 * Tests for electron/mac-rebuilt-app.cjs — resolving the rebuilt macOS `.app`
 * bundle for the in-app update swap/relaunch.
 *
 * Run with: node --test electron/mac-rebuilt-app.test.cjs
 * (Wired into npm test:desktop:platforms in package.json.)
 *
 * Why this matters: electron-builder writes the rebuilt bundle under an
 * arch-specific dir. The updater used to look only at `mac-arm64` and `mac`, so
 * an Intel rebuild in `release/mac-x64` was missed and the update never
 * installed — it degraded to "Restart Hermes to load the new version"
 * (issue #48160). Resolution must follow the host arch.
 */

const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

const { resolveRebuiltMacApp } = require('./mac-rebuilt-app.cjs')

const ROOT = '/install'
const bundle = dir => path.join(ROOT, 'apps', 'desktop', 'release', dir, 'Hermes.app')
const onlyExists = (...present) => p => present.includes(p)

test('an Intel/x64 rebuild resolves release/mac-x64 (issue #48160)', () => {
  const exists = onlyExists(bundle('mac-x64'))
  assert.equal(resolveRebuiltMacApp(ROOT, { arch: 'x64', exists }), bundle('mac-x64'))
})

test('an Apple Silicon rebuild resolves release/mac-arm64', () => {
  const exists = onlyExists(bundle('mac-arm64'))
  assert.equal(resolveRebuiltMacApp(ROOT, { arch: 'arm64', exists }), bundle('mac-arm64'))
})

test('a host-arch (no explicit arch) build falls back to release/mac', () => {
  const exists = onlyExists(bundle('mac'))
  assert.equal(resolveRebuiltMacApp(ROOT, { arch: 'x64', exists }), bundle('mac'))
  assert.equal(resolveRebuiltMacApp(ROOT, { arch: 'arm64', exists }), bundle('mac'))
})

test('an Intel host never selects a stale mac-arm64 bundle', () => {
  // Both arch dirs present (e.g. leftover from a prior cross-build): an x64
  // host must install the x64 bundle, not the arm64 one.
  const exists = onlyExists(bundle('mac-arm64'), bundle('mac-x64'))
  assert.equal(resolveRebuiltMacApp(ROOT, { arch: 'x64', exists }), bundle('mac-x64'))
})

test('a non-x64/non-arm64 arch only considers the generic release/mac dir', () => {
  // An unexpected process.arch must not guess an arch-specific dir, even when
  // arch dirs exist on disk — it falls back to release/mac only.
  const exists = onlyExists(bundle('mac-arm64'), bundle('mac-x64'), bundle('mac'))
  assert.equal(resolveRebuiltMacApp(ROOT, { arch: 'ppc64', exists }), bundle('mac'))
})

test('returns undefined when no rebuilt bundle exists', () => {
  assert.equal(resolveRebuiltMacApp(ROOT, { arch: 'x64', exists: () => false }), undefined)
})
