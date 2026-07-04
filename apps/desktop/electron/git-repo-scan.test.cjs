'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const { scanGitRepos } = require('./git-repo-scan.cjs')

function mkTmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-git-repo-scan-'))
}

// Create a fake repo: a directory containing a real `.git` directory.
function mkRepo(root, ...segments) {
  const repo = path.join(root, ...segments)
  fs.mkdirSync(path.join(repo, '.git'), { recursive: true })
  return repo
}

function foundRoots(results) {
  return results.map(entry => entry.root).sort()
}

test('scanGitRepos finds a normal repo but skips root-level macOS media folders', async () => {
  const root = mkTmpDir()

  try {
    const dev = mkRepo(root, 'dev', 'proj')
    // Repos inside the TCC-protected home-root media folders must not be
    // crawled (descending into them triggers permission prompts).
    mkRepo(root, 'Pictures', 'wallpapers')
    mkRepo(root, 'Music', 'samples')
    mkRepo(root, 'Movies', 'clips')
    mkRepo(root, 'Public', 'shared')

    const results = await scanGitRepos([root])

    assert.deepEqual(foundRoots(results), [dev])
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('scanGitRepos still scans a media-named directory that is not at the root level', async () => {
  const root = mkTmpDir()

  try {
    // ~/dev/Music is an ordinary directory that merely shares the name; only
    // the DIRECT child of a search root is the TCC-protected instance.
    const nested = mkRepo(root, 'dev', 'Music', 'app')

    const results = await scanGitRepos([root])

    assert.deepEqual(foundRoots(results), [nested])
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('scanGitRepos skips Apple library packages at any depth', async () => {
  const root = mkTmpDir()

  try {
    const keeper = mkRepo(root, 'code', 'site')
    // Library packages are plain directories to readdir but TCC-protected;
    // they must be skipped even when nested (e.g. on a non-default path) and
    // regardless of case.
    mkRepo(root, 'code', 'Photos Library.photoslibrary', 'inner')
    mkRepo(root, 'backups', 'Music Library.MUSICLIBRARY', 'inner')
    mkRepo(root, 'backups', 'TV Library.tvlibrary', 'inner')
    mkRepo(root, 'backups', 'Old.aplibrary', 'inner')

    const results = await scanGitRepos([root])

    assert.deepEqual(foundRoots(results), [keeper])
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('scanGitRepos walks an explicitly passed media root', async () => {
  const root = mkTmpDir()

  try {
    // The root-level skip applies to children of a search root, not to the
    // root itself: a user explicitly scanning ~/Music opted in.
    const musicRoot = path.join(root, 'Music')
    const repo = mkRepo(musicRoot, 'samples')

    const results = await scanGitRepos([musicRoot])

    assert.deepEqual(foundRoots(results), [repo])
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})
