import { SSMClient, GetParameterCommand, PutParameterCommand } from '@aws-sdk/client-ssm'
import { logger } from '../utils/logger'

/**
 * Get a parameter from AWS Systems Manager Parameter Store.
 */
export const getParameter = async (name: string) => {
  try {
    const client = new SSMClient({ region: process.env.AWS_REGION })
    const command = new GetParameterCommand({ Name: name, WithDecryption: true })

    const { Parameter } = await client.send(command)

    return Parameter.Value
  } catch (error) {
    if (error.name === 'ParameterNotFound') {
      return ''
    }
    logger.error(error)
    throw error
  }
}

/**
 * Put a parameter to AWS Systems Manager Parameter Store.
 */
export const setParameter = async (name: string, value: string) => {
  try {
    const client = new SSMClient({ region: process.env.AWS_REGION })
    const command = new PutParameterCommand({
      Name: name,
      Value: value,
      Type: 'SecureString',
      Overwrite: true
    })
    return client.send(command)
  } catch (error) {
    logger.error(error)
    throw error
  }
}
