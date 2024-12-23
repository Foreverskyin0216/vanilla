import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import { DynamoDBDocumentClient, QueryCommand, PutCommand, DeleteCommand } from '@aws-sdk/lib-dynamodb'

export interface Message {
  thread_id: string
  created_at: number
  content: string
}

export interface Thread {
  id: string
  conversation_id: string
}

/**
 * Get all messages in a chat thread.
 *
 * @param {string} thread_id - The chat thread ID.
 */
export const getMessages = async (thread_id: string) => {
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
  const queryCommand = new QueryCommand({
    TableName: 'Message',
    KeyConditionExpression: '#thread_id = :thread_id',
    ExpressionAttributeNames: { '#thread_id': 'thread_id' },
    ExpressionAttributeValues: { ':thread_id': thread_id },
    ScanIndexForward: true
  })

  const { Items } = await client.send(queryCommand)

  return (Items ? Items : []) as Message[]
}

/**
 * Store a message to a chat group. The created_at field will be automatically generated.
 *
 * @param {Object} message - The message to store.
 * @param {string} [message.thread_id] - The chat group ID.
 * @param {string} [message.content] - The message content.
 */
export const storeMessage = async (message: Omit<Message, 'created_at'>) => {
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
  const putCommand = new PutCommand({ TableName: 'Message', Item: { ...message, created_at: Date.now() } })
  return client.send(putCommand)
}

/**
 * Clear all messages in a chat thread.
 *
 * @param {string} thread_id - The thread Id used to find all messages to delete.
 */
export const clearMessages = async (thread_id: string) => {
  const messages = await getMessages(thread_id)
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
  return Promise.all(
    messages.map(({ created_at }) => {
      const command = new DeleteCommand({ TableName: 'Message', Key: { thread_id, created_at } })
      const request = client.send(command)
      return request
    })
  )
}

export const clearThread = async (id: string) => {
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
  const command = new DeleteCommand({ TableName: 'Thread', Key: { id } })
  return client.send(command)
}

/**
 * Get the thread of a chat group.
 *
 * @param {string} id - The chat thread ID.
 */
export const getThread = async (id: string) => {
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
  const queryCommand = new QueryCommand({
    TableName: 'Thread',
    KeyConditionExpression: 'id = :id',
    ExpressionAttributeValues: { ':id': id }
  })

  const { Items } = await client.send(queryCommand)

  return Items?.length ? (Items[0] as Thread) : undefined
}

/**
 * Set the thread of a chat group.
 *
 * @param {Object} configuration - The thread data to set.
 * @param {string} [configuration.id] - The chat thread ID.
 */
export const setThread = async (thread: Thread) => {
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
  const putCommand = new PutCommand({ TableName: 'Thread', Item: thread })
  return client.send(putCommand)
}
