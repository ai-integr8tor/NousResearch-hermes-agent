const test = require('node:test')
const assert = require('node:assert/strict')

const {
  profileDeleteTargetFromRequest,
  profileRenameFromRequest
} = require('./profile-request-routing.cjs')

test('profileDeleteTargetFromRequest parses profile delete target', () => {
  assert.equal(
    profileDeleteTargetFromRequest({ method: 'DELETE', path: '/api/profiles/Work%20Profile' }),
    'work profile'
  )
  assert.equal(profileDeleteTargetFromRequest({ method: 'GET', path: '/api/profiles/work' }), null)
})

test('profileRenameFromRequest parses profile rename source and target', () => {
  assert.deepEqual(
    profileRenameFromRequest({
      method: 'PATCH',
      path: '/api/profiles/yabaiyan-creator-profile',
      body: JSON.stringify({ new_name: 'yabaiyan-profile' })
    }),
    { oldName: 'yabaiyan-creator-profile', newName: 'yabaiyan-profile' }
  )
})

test('profileRenameFromRequest accepts already-parsed JSON bodies', () => {
  assert.deepEqual(
    profileRenameFromRequest({
      method: 'PATCH',
      path: '/api/profiles/local-lufei',
      body: { new_name: 'gpt5-local-lufei' }
    }),
    { oldName: 'local-lufei', newName: 'gpt5-local-lufei' }
  )
})

test('profileRenameFromRequest ignores malformed rename requests', () => {
  assert.equal(profileRenameFromRequest({ method: 'DELETE', path: '/api/profiles/a', body: '{}' }), null)
  assert.equal(profileRenameFromRequest({ method: 'PATCH', path: '/api/profiles/a', body: '{}' }), null)
  assert.equal(profileRenameFromRequest({ method: 'PATCH', path: '/api/profiles/default', body: '{"new_name":"x"}' }), null)
  assert.equal(profileRenameFromRequest({ method: 'PATCH', path: '/api/profiles/a', body: '{"new_name":"default"}' }), null)
})
