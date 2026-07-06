const assert = require('node:assert/strict')
const { test } = require('node:test')

const {
  DEFAULT_MENU_BAR_COMMAND_REFERENCE_ENABLED,
  menuBarCommandReferenceEnabledFromConfig
} = require('./menu-bar-command-reference.cjs')

test('menu bar command reference defaults on for missing or malformed config', () => {
  assert.equal(DEFAULT_MENU_BAR_COMMAND_REFERENCE_ENABLED, true)
  assert.equal(menuBarCommandReferenceEnabledFromConfig(null), true)
  assert.equal(menuBarCommandReferenceEnabledFromConfig({}), true)
  assert.equal(menuBarCommandReferenceEnabledFromConfig({ enabled: 'false' }), true)
})

test('menu bar command reference accepts an explicit disabled setting', () => {
  assert.equal(menuBarCommandReferenceEnabledFromConfig({ enabled: false }), false)
  assert.equal(menuBarCommandReferenceEnabledFromConfig({ enabled: true }), true)
})
