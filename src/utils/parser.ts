import { readFileSync } from 'fs'
import { join } from 'path'

import yaml from 'yaml'
import minimist from 'minimist'

import { logger } from './logger'

interface Command {
  name: string
  parameters?: CommandParameter[]
}

interface CommandParameter {
  name: string
  alias?: string
  default?: string
  options?: string[]
}

/**
 * Parse debug command.
 */
export const parseDebugCommand = (message: string) => {
  try {
    const args = message.split(/\s+(?=(?:[^"]*"[^"]*")*[^"]*$)/).map((arg) => arg.replaceAll('"', ''))

    const filePath = join(__dirname, './debug-commands.yml')
    const { commands } = yaml.parse(readFileSync(filePath, 'utf8')) as { commands: Command[] }
    const command = commands.find(({ name }) => name === args[1])

    const minimistOpts = command.parameters?.reduce(
      (acc, { name, alias, default: defaultValue }) => {
        if (alias !== undefined) acc.alias[alias] = name
        if (defaultValue !== undefined) acc.default[name] = defaultValue
        return acc
      },
      { alias: {}, default: {} }
    )
    const parsed = minimist(args.slice(1), minimistOpts)
    const params = Object.entries(parsed).reduce(
      (acc, [key, value]) => {
        if (!minimistOpts?.alias?.[key]) acc[key] = value
        return acc
      },
      {} as { [key: string]: string }
    )
    delete params._

    const parsedParams = command.parameters?.reduce(
      (acc, { name, default: defaultValue, options }) => {
        acc[name] = options?.includes(params[name]) ? params[name] : defaultValue
        return acc
      },
      {} as { [key: string]: string }
    )

    return { command: command.name, params: parsedParams }
  } catch (error) {
    if (error.name === 'TypeError') {
      return { error: 'Invalid command format' }
    }
    logger.error(error)
    throw error
  }
}
