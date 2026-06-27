function isValidActionIndex(index, actions) {
  return Number.isInteger(index) && index >= 0 && index < actions.length
}

function notificationActionIndex(actionEvent, legacyIndex) {
  if (actionEvent && typeof actionEvent === 'object') {
    const detailsIndex = actionEvent.actionIndex

    if (Number.isInteger(detailsIndex)) {
      return detailsIndex
    }
  }

  if (Number.isInteger(legacyIndex)) {
    return legacyIndex
  }

  return null
}

function resolveNotificationAction(actions, actionEvent, legacyIndex) {
  if (!Array.isArray(actions)) {
    return null
  }

  const index = notificationActionIndex(actionEvent, legacyIndex)

  if (!isValidActionIndex(index, actions)) {
    return null
  }

  return actions[index] || null
}

module.exports = {
  notificationActionIndex,
  resolveNotificationAction
}
