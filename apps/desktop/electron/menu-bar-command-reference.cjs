const DEFAULT_MENU_BAR_COMMAND_REFERENCE_ENABLED = true

function menuBarCommandReferenceEnabledFromConfig(config) {
  if (!config || typeof config !== 'object' || Array.isArray(config)) {
    return DEFAULT_MENU_BAR_COMMAND_REFERENCE_ENABLED
  }

  return typeof config.enabled === 'boolean' ? config.enabled : DEFAULT_MENU_BAR_COMMAND_REFERENCE_ENABLED
}

module.exports = {
  DEFAULT_MENU_BAR_COMMAND_REFERENCE_ENABLED,
  menuBarCommandReferenceEnabledFromConfig
}
