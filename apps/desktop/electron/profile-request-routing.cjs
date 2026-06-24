const PROFILE_PATH_RE = /^\/api\/profiles\/([^/?#]+)(?:[?#].*)?$/

function profileNameFromPath(path) {
  const match = String(path || '').match(PROFILE_PATH_RE)
  if (!match) {
    return null
  }

  let raw = ''
  try {
    raw = decodeURIComponent(match[1])
  } catch {
    return null
  }

  const name = raw.trim()
  if (!name) {
    return null
  }
  if (name.toLowerCase() === 'default') {
    return 'default'
  }
  return name.toLowerCase()
}

function profileDeleteTargetFromRequest(request) {
  if (!request || String(request.method || 'GET').toUpperCase() !== 'DELETE') {
    return null
  }

  return profileNameFromPath(request.path)
}

function parseJsonBody(body) {
  if (body == null || body === '') {
    return {}
  }
  if (typeof body === 'object') {
    return body
  }
  try {
    return JSON.parse(String(body))
  } catch {
    return {}
  }
}

function profileRenameFromRequest(request) {
  if (!request || String(request.method || 'GET').toUpperCase() !== 'PATCH') {
    return null
  }

  const oldName = profileNameFromPath(request.path)
  if (!oldName || oldName === 'default') {
    return null
  }

  const body = parseJsonBody(request.body)
  const newName = String(body.new_name || '').trim().toLowerCase()
  if (!newName || newName === 'default') {
    return null
  }

  return { oldName, newName }
}

module.exports = {
  profileDeleteTargetFromRequest,
  profileNameFromPath,
  profileRenameFromRequest
}
