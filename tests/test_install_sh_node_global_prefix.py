"""Regression tests for the Hermes-managed Node's npm exposure.

When the installer falls back to a bundled Node under ``$HERMES_HOME/node``,
it must remain private for user-scoped installs so it does not shadow nvm/fnm/
proto in later shells. Root FHS installs are the exception: they intentionally
expose managed node/npm/npx in /usr/local/bin for root shell reachability.
"""

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
NODE_BOOTSTRAP = REPO_ROOT / "scripts" / "lib" / "node-bootstrap.sh"


def _write_executable(path: Path, body: str = "#!/bin/sh\nexit 0\n") -> None:
    path.write_text(body)
    path.chmod(0o755)


def test_install_sh_scopes_bundled_npm_prefix_by_layout() -> None:
    text = INSTALL_SH.read_text()

    assert "configure_managed_node_npm_prefix()" in text
    assert 'prefix="$(dirname "$(get_command_link_dir)")"' in text
    assert 'prefix="$HERMES_HOME/node"' in text


def test_install_sh_repairs_existing_managed_node_on_rerun() -> None:
    """The redirect must run on every install (not just fresh Node installs),
    so re-running the installer repairs pre-existing managed installs whose
    Node is already up to date and would otherwise skip install_node."""
    text = INSTALL_SH.read_text()

    check_node_body = text.split("check_node()", 1)[1].split("\ninstall_node()", 1)[0]
    assert "configure_managed_node_npm_prefix" in check_node_body

    # No-op guard so it's safe to call when there is no managed Node.
    assert '[ -x "$HERMES_HOME/node/bin/npm" ] || return 0' in text
    assert "remove_private_managed_node_links" in check_node_body


def test_node_bootstrap_scopes_bundled_npm_prefix_by_layout() -> None:
    text = NODE_BOOTSTRAP.read_text()

    assert "_nb_configure_npm_prefix()" in text
    assert '_prefix="$(dirname "$(_nb_get_link_dir)")"' in text
    assert '_prefix="$HERMES_HOME/node"' in text

    # Runs at the top of ensure_node so existing managed installs are repaired
    # even when a modern Node is already present (early return path).
    ensure_node_body = text.split("ensure_node()", 1)[1]
    assert "_nb_configure_npm_prefix" in ensure_node_body
    assert "_nb_remove_private_managed_node_links" in ensure_node_body
    assert '[ -x "$HERMES_HOME/node/bin/npm" ] || return 0' in text
    assert "heal_managed_node()" in text
    assert "_nb_managed_tool_broken" in text
    assert "for tool in node npm npx" in text


def test_install_sh_does_not_unconditionally_link_managed_node_tools() -> None:
    """The managed Node fallback must not shadow user version managers.

    Non-root desktop installs add the Hermes command dir to shell PATH. If the
    fallback Node also places node/npm/npx there, a later shell can resolve
    Hermes's Node before nvm/fnm/proto.
    """
    text = INSTALL_SH.read_text()
    install_node_body = text.split("install_node()", 1)[1].split(
        "\ncheck_network_prerequisites()", 1
    )[0]

    assert 'ln -sf "$HERMES_HOME/node/bin/node" "$node_link_dir/node"' not in install_node_body
    assert 'ln -sf "$HERMES_HOME/node/bin/npm"  "$node_link_dir/npm"' not in install_node_body
    assert 'ln -sf "$HERMES_HOME/node/bin/npx"  "$node_link_dir/npx"' not in install_node_body


def test_node_bootstrap_does_not_unconditionally_link_managed_node_tools() -> None:
    text = NODE_BOOTSTRAP.read_text()
    install_body = text.split("_nb_install_bundled_node()", 1)[1].split(
        "\n# ---------------------------------------------------------------------------\n# Heal", 1
    )[0]

    assert 'ln -sf "$HERMES_HOME/node/bin/node" "$_link_dir/node"' not in install_body
    assert 'ln -sf "$HERMES_HOME/node/bin/npm"  "$_link_dir/npm"' not in install_body
    assert 'ln -sf "$HERMES_HOME/node/bin/npx"  "$_link_dir/npx"' not in install_body


def test_node_bootstrap_removes_legacy_private_links(tmp_path: Path) -> None:
    home = tmp_path / "home"
    hermes_home = tmp_path / "hermes"
    link_dir = home / ".local" / "bin"
    managed_bin = hermes_home / "node" / "bin"
    link_dir.mkdir(parents=True)
    managed_bin.mkdir(parents=True)

    for tool in ("node", "npm", "npx"):
        _write_executable(managed_bin / tool)
        (link_dir / tool).symlink_to(managed_bin / tool)

    script = f"""
set -e
export HOME={home}
export HERMES_HOME={hermes_home}
source {NODE_BOOTSTRAP}
_nb_configure_npm_prefix
_nb_remove_private_managed_node_links
for tool in node npm npx; do
  test ! -e "$HOME/.local/bin/$tool"
done
grep -qx "prefix=$HERMES_HOME/node" "$HERMES_HOME/node/etc/npmrc"
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
