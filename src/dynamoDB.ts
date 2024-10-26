import { DynamoDBClient } from '@aws-sdk/client-dynamodb'
import { DynamoDBDocumentClient, QueryCommand, PutCommand, DeleteCommand } from '@aws-sdk/lib-dynamodb'

interface Message {
  thread_id: string
  created_at: number
  content: string
}

interface Thread {
  id: string
  conversation_id: string
}

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

export const storeMessage = async (message: Omit<Message, 'created_at'>) => {
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
  const putCommand = new PutCommand({ TableName: 'Message', Item: { ...message, created_at: Date.now() } })
  return client.send(putCommand)
}

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

export const setThread = async (thread: Thread) => {
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
  const putCommand = new PutCommand({ TableName: 'Thread', Item: thread })
  return client.send(putCommand)
}
