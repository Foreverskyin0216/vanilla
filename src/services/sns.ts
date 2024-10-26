import { SNSClient, PublishCommand } from '@aws-sdk/client-sns'
import { logger } from '../utils/logger'

export const publishMessage = async (topicArn: string, message: string) => {
  try {
    const client = new SNSClient({ region: process.env.AWS_REGION })
    const command = new PublishCommand({ TopicArn: topicArn, Message: message })
    return client.send(command)
  } catch (error) {
    logger.error(error)
    throw error
  }
}
