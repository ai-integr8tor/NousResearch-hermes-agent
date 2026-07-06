const assert = require('node:assert/strict')
const { test } = require('node:test')
const path = require('node:path')
const { pathToFileURL } = require('node:url')

const { buildSlashReferenceWindowUrl, positionSlashReferenceWindowBounds } = require('./slash-reference-window.cjs')

test('buildSlashReferenceWindowUrl targets the dev renderer menu-bar route', () => {
  assert.equal(
    buildSlashReferenceWindowUrl({ devServer: 'http://127.0.0.1:5174/' }),
    'http://127.0.0.1:5174/?win=slash-reference#/'
  )
})

test('buildSlashReferenceWindowUrl targets the packaged renderer menu-bar route', () => {
  const index = path.join('/tmp', 'Hermes.app', 'Contents', 'Resources', 'app.asar', 'dist', 'index.html')

  assert.equal(
    buildSlashReferenceWindowUrl({ rendererIndexPath: index }),
    `${pathToFileURL(index).toString()}?win=slash-reference#/`
  )
})

test('positionSlashReferenceWindowBounds centers below the tray icon and clamps to screen edges', () => {
  const bounds = positionSlashReferenceWindowBounds({
    displayBounds: { x: 0, y: 0, width: 500, height: 900 },
    trayBounds: { x: 450, y: 0, width: 28, height: 24 },
    windowSize: { width: 420, height: 640 }
  })

  assert.equal(bounds.x, 72)
  assert.equal(bounds.y, 32)
  assert.equal(bounds.width, 420)
  assert.equal(bounds.height, 640)
})

test('positionSlashReferenceWindowBounds opens above the tray when there is no room below', () => {
  const bounds = positionSlashReferenceWindowBounds({
    displayBounds: { x: 100, y: 100, width: 800, height: 500 },
    trayBounds: { x: 420, y: 560, width: 28, height: 24 },
    windowSize: { width: 360, height: 300 }
  })

  assert.equal(bounds.x, 254)
  assert.equal(bounds.y, 252)
})
