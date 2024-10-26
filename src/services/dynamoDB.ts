import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import { DynamoDBDocumentClient, QueryCommand, PutCommand, DeleteCommand } from '@aws-sdk/lib-dynamodb'
import { logger } from '../utils/logger'

interface Message {
  groupId: string
  createdAt: number
  content: string
}

/**
 * Get chat history within a specific number of days.
 *
 * @param groupId The chat group ID.
 * @param days The number of days to look back.
 */
export const getMessages = async (groupId: string, days?: number) => {
  try {
    const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
    const command = new QueryCommand({
      TableName: 'Message',
      KeyConditionExpression: 'groupId = :groupId' + (days ? ' AND createdAt BETWEEN :start AND :end' : ''),
      ExpressionAttributeValues: {
        ':groupId': groupId,
        ...(days ? { ':start': Date.now() - days * 24 * 60 * 60 * 1000, ':end': Date.now() } : {})
      },
      ScanIndexForward: true
    })

    const { Items } = await client.send(command)

    return Items as Message[]
  } catch (error) {
    if (error.name === 'ResourceNotFoundException') {
      return []
    }
    logger.error(error)
    throw error
  }
}

/**
 * Store a message to a chat group.
 */
export const storeMessage = async (message: Omit<Message, 'createdAt'>) => {
  try {
    const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
    const command = new PutCommand({ TableName: 'Message', Item: { ...message, createdAt: Date.now() } })

    return client.send(command)
  } catch (error) {
    logger.error(error)
    throw error
  }
}

/**
 * Clear all messages in a chat group.
 */
export const clearMessages = async (groupId: string) => {
  try {
    const messages = await getMessages(groupId)
    const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))

    return Promise.all(
      messages.map(({ createdAt }) =>
        client.send(new DeleteCommand({ TableName: 'Message', Key: { groupId, createdAt } }))
      )
    )
  } catch (error) {
    logger.error(error)
    throw error
  }
}
