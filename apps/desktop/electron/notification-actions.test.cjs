const assert = require('node:assert/strict')
const test = require('node:test')

const { notificationActionIndex, resolveNotificationAction } = require('./notification-actions.cjs')

const actions = [
  { id: 'approve', text: 'Approve' },
  { id: 'reject', text: 'Reject' }
]

test('notificationActionIndex reads Electron 40 actionIndex details', () => {
  assert.equal(notificationActionIndex({ actionIndex: 1 }, undefined), 1)
})

test('notificationActionIndex keeps the legacy second argument fallback', () => {
  assert.equal(notificationActionIndex({}, 0), 0)
})

test('notificationActionIndex prefers Electron details over the deprecated argument', () => {
  assert.equal(notificationActionIndex({ actionIndex: 1 }, 0), 1)
})

test('resolveNotificationAction selects the action from Electron 40 details', () => {
  assert.deepEqual(resolveNotificationAction(actions, { actionIndex: 0 }, undefined), actions[0])
})

test('resolveNotificationAction selects the action from the legacy index argument', () => {
  assert.deepEqual(resolveNotificationAction(actions, {}, 1), actions[1])
})

test('resolveNotificationAction ignores missing and out-of-range indexes', () => {
  assert.equal(resolveNotificationAction(actions, {}, undefined), null)
  assert.equal(resolveNotificationAction(actions, { actionIndex: 2 }, undefined), null)
  assert.equal(resolveNotificationAction(actions, { actionIndex: -1 }, undefined), null)
})
