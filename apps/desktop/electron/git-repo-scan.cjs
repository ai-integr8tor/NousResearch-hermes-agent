'use strict'

// Repo-first discovery: walk bounded roots for git repos using only Node's `fs`
// — no native addon, so it just works for anyone who pulls main (no
// electron-rebuild). Mirrors how GitHub Desktop scans: stop at the first `.git`
// (don't descend into a repo), cap depth, and skip heavy non-repo trees so the
// first scan stays fast. Results are cached by the backend after the first run.

const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const fsp = fs.promises

// Shallow on purpose: real projects live a few levels under home
// (`~/www/repo`, `~/code/org/repo`); deeper `.git` dirs are almost always
// fixtures/vendored/eval checkouts (e.g. `~/www/ha-evals/tasks/*/repo`). Repos
// you actually use but keep deeper still surface via session-derived discovery,
// so this only prunes noise, never repos with history.
const DEFAULT_MAX_DEPTH = 3
const MAX_CONCURRENCY = 32

// Big trees that are never themselves repos and would waste the walk. Anything
// hidden (dotdirs like .cache/.Trash/.npm) is skipped wholesale below, so this
// only needs the non-hidden heavyweights.
const JUNK_DIRS = new Set(['Applications', 'Library', 'node_modules', 'site-packages', 'vendor', 'venv'])

// macOS TCC-protected media folders: descending into ~/Pictures, ~/Music,
// ~/Movies (or reading ~/Public) triggers per-service permission prompts
// (Photos, Media Library, Files & Folders) attributed to the app. Skipped only
// as DIRECT children of a search root — the protected instances live at the
// home-dir top level, while a nested dir that merely shares the name
// (~/dev/Music-app, ~/code/Movies) is ordinary and may hold real repos.
// A root the user passes explicitly (e.g. roots: ['~/Music']) is still walked.
const MEDIA_ROOT_DIRS = new Set(['Movies', 'Music', 'Pictures', 'Public'])

// Apple media-library packages (Photos, Music, TV, Aperture) look like plain
// directories to readdir but are TCC-protected and never contain user repos.
// Skip them at ANY depth — Photos libraries in particular often live on
// external volumes or non-default paths.
const LIBRARY_PACKAGE_SUFFIXES = ['.photoslibrary', '.musiclibrary', '.tvlibrary', '.aplibrary']

function isLibraryPackage(name) {
  const lower = String(name).toLowerCase()
  return LIBRARY_PACKAGE_SUFFIXES.some(suffix => lower.endsWith(suffix))
}

async function mapLimit(items, limit, fn) {
  let cursor = 0

  async function worker() {
    while (cursor < items.length) {
      const index = cursor
      cursor += 1
      await fn(items[index])
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker))
}

/**
 * Scan `roots` (default: the home dir) for git repositories. Returns deduped
 * `{ root, label }` entries. `options.maxDepth` caps recursion (default 3).
 */
async function scanGitRepos(roots, options = {}) {
  const maxDepth = Number(options.maxDepth) || DEFAULT_MAX_DEPTH
  const searchRoots = Array.isArray(roots) && roots.length > 0 ? roots : [os.homedir()]
  const found = new Map()

  async function walk(dir, depth) {
    if (depth > maxDepth) {
      return
    }

    let entries
    try {
      entries = await fsp.readdir(dir, { withFileTypes: true })
    } catch {
      return // unreadable / permission denied
    }

    // A `.git` DIRECTORY marks a real repo root (a main checkout). A `.git`
    // FILE is a linked worktree or submodule — those belong to their parent
    // repo as lanes, not as separate projects, so we don't list them (and we
    // keep descending in case a real repo sits deeper). This is what kills the
    // worktree/eval-repo duplicate explosion.
    if (entries.some(entry => entry.name === '.git' && entry.isDirectory())) {
      const root = dir.replace(/[/\\]+$/, '')
      found.set(root, path.basename(root) || root)

      return
    }

    const subdirs = []
    for (const entry of entries) {
      // Real directories only (skip symlinks to avoid loops), no hidden dirs, no
      // known heavy trees.
      if (!entry.isDirectory() || entry.name.startsWith('.') || JUNK_DIRS.has(entry.name)) {
        continue
      }

      // depth 0 = entries directly under a search root (the home dir by
      // default): don't descend into the TCC-protected media folders there.
      if (depth === 0 && MEDIA_ROOT_DIRS.has(entry.name)) {
        continue
      }

      if (isLibraryPackage(entry.name)) {
        continue
      }

      subdirs.push(path.join(dir, entry.name))
    }

    await mapLimit(subdirs, MAX_CONCURRENCY, sub => walk(sub, depth + 1))
  }

  await mapLimit(searchRoots.map(root => String(root || '').trim()).filter(Boolean), MAX_CONCURRENCY, root =>
    walk(root, 0)
  )

  return [...found.entries()].map(([root, label]) => ({ label, root }))
}

module.exports = { scanGitRepos }
