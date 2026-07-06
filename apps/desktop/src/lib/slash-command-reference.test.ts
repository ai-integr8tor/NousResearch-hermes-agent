import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import {
  SLASH_REFERENCE_DYNAMIC_ROUTES_NOTE,
  type SlashReferenceCommand,
  slashReferenceCommands,
  slashReferenceDisplayDescription,
  slashReferenceSections,
  slashReferenceSurfaceTag
} from './slash-command-reference'

interface ExtractedCommand {
  aliases: string[]
  argsHint: string
  category: string
  cliOnly: boolean
  description: string
  gatewayConfigGate: null | string
  gatewayOnly: boolean
  name: string
  subcommands: string[]
}

function repoRoot(): string {
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
}

function extractedRegistry(): ExtractedCommand[] {
  const root = repoRoot()

  const result = spawnSync(
    'python3',
    [path.join(root, 'apps/desktop/scripts/extract-command-registry.py'), path.join(root, 'hermes_cli/commands.py')],
    { encoding: 'utf8' }
  )

  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || 'extract-command-registry.py failed')
  }

  return JSON.parse(result.stdout) as ExtractedCommand[]
}

describe('slash command reference data', () => {
  it('tracks every canonical command from COMMAND_REGISTRY in registry order', () => {
    const registry = extractedRegistry()

    expect(slashReferenceCommands.map(command => command.name)).toEqual(registry.map(command => command.name))
    expect(slashReferenceCommands).toHaveLength(registry.length)
  })

  it('keeps registry metadata intact for aliases, args, descriptions, and categories', () => {
    const registry = extractedRegistry()

    for (const expected of registry) {
      const actual: SlashReferenceCommand | undefined = slashReferenceCommands.find(
        command => command.name === expected.name
      )

      expect({
        aliases: actual?.aliases ?? [],
        argsHint: actual?.argsHint ?? '',
        category: actual?.category,
        description: actual?.description,
        gatewayConfigGate: actual?.gatewayConfigGate ?? null,
        subcommands: actual?.subcommands ?? []
      }).toEqual({
        aliases: expected.aliases,
        argsHint: expected.argsHint,
        category: expected.category,
        description: expected.description,
        gatewayConfigGate: expected.gatewayConfigGate,
        subcommands: expected.subcommands
      })
    }
  })

  it('derives screenshot-style surface tags from registry fields', () => {
    expect(slashReferenceSurfaceTag(slashReferenceCommands.find(command => command.name === 'clear')!)).toBe('cli')
    expect(slashReferenceSurfaceTag(slashReferenceCommands.find(command => command.name === 'approve')!)).toBe('chat')
    expect(slashReferenceSurfaceTag(slashReferenceCommands.find(command => command.name === 'verbose')!)).toBe('cfg')
    expect(slashReferenceSurfaceTag(slashReferenceCommands.find(command => command.name === 'retry')!)).toBe('both')
  })

  it('keeps compact display copy separate from registry metadata', () => {
    const newCommand = slashReferenceCommands.find(command => command.name === 'new')!
    const undoCommand = slashReferenceCommands.find(command => command.name === 'undo')!

    expect(newCommand.description).toContain('fresh session ID')
    expect(slashReferenceDisplayDescription(newCommand)).toBe('Start a new session')
    expect(slashReferenceDisplayDescription(undoCommand)).toBe('Back up/remove turn')
  })

  it('groups registry categories into the quick-reference sections', () => {
    expect(slashReferenceSections.map(section => section.title)).toEqual([
      'Session / Flow',
      'Config',
      'Tools / Skills',
      'Info / Exit'
    ])

    const infoExit = slashReferenceSections.find(section => section.title === 'Info / Exit')!

    expect(infoExit.commands.map(command => command.name)).toContain('quit')
  })

  it('keeps the dynamic routes note visible', () => {
    expect(SLASH_REFERENCE_DYNAMIC_ROUTES_NOTE).toContain('/<skill-name>')
    expect(SLASH_REFERENCE_DYNAMIC_ROUTES_NOTE).toContain('quick commands')
  })
})
