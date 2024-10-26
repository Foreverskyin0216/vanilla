import { Logger } from '@aws-lambda-powertools/logger'

/**
 * A Shared Logger instance that can be used across the application.
 */
export const logger = new Logger({ serviceName: 'Vanilla', logLevel: 'INFO' })
