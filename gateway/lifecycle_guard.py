"""Gateway lifecycle command detection shared by CLI and tools."""

from __future__ import annotations

import re

# Patterns that indicate a command targets the Hermes gateway lifecycle.
# Deliberately specific: a bare "gateway ... restart" catch-all would block
# legitimate prompts that merely mention unrelated gateways.
GATEWAY_LIFECYCLE_COMMAND_RE = re.compile(
    r"(?i)"
    r"(hermes\s+gateway\s+(restart|stop|start))"
    r"|(launchctl\s+(kickstart|unload|load|stop|restart)\s+.*hermes)"
    r"|(systemctl\s+(-\S+\s+)*(restart|stop|start)\s+.*hermes)"
    r"|(p?kill\s+.*hermes.*gateway)"
)


def contains_gateway_lifecycle_command(text: str) -> bool:
    """Return True if *text* contains a Hermes gateway lifecycle command."""
    return bool(GATEWAY_LIFECYCLE_COMMAND_RE.search(text or ""))
