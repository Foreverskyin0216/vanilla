import { type DynamoDBClientConfig, DynamoDBClient } from '@aws-sdk/client-dynamodb'
import {
  DynamoDBDocumentClient,
  GetCommand,
  QueryCommand,
  PutCommand,
  BatchWriteCommand,
  DeleteCommand
} from '@aws-sdk/lib-dynamodb'

import { type LangGraphRunnableConfig as RunnableConfig } from '@langchain/langgraph'
import {
  type Checkpoint,
  type CheckpointMetadata,
  type CheckpointTuple,
  type PendingWrite,
  type SerializerProtocol,
  BaseCheckpointSaver
} from '@langchain/langgraph-checkpoint'

import { logger } from '../utils/logger'

interface Message {
  groupId: string
  createdAt: number
  content: string
}

interface Configuration {
  groupId: string
  chatMode: string
  modelName: string
}

/**
 * ### Implement a DynamoDB Saver as a LangGraph checkpointer.
 *
 * @class DynamoDBSaver
 * @extends {BaseCheckpointSaver} LangGraph base checkpointer.
 *
 * @param {Object} params - The parameters for the constructor.
 * @param {DynamoDBClientConfig} [params.dynamoDBClientConfig] - Optional configuration for the DynamoDB client.
 * @param {SerializerProtocol} [params.serde] - Optional serializer protocol for serializing and deserializing data.
 */
class DynamoDBSaver extends BaseCheckpointSaver {
  client: DynamoDBDocumentClient
  checkpoints: string = 'Checkpoints'
  checkpointWrites: string = 'CheckpointWrites'
  separator: string = ':::'

  constructor(params: { clientConfig?: DynamoDBClientConfig; serde?: SerializerProtocol }) {
    super(params.serde)
    this.client = DynamoDBDocumentClient.from(new DynamoDBClient(params.clientConfig))
  }

  async getTuple(config: RunnableConfig): Promise<CheckpointTuple> {
    const getItem = async ({ thread_id, checkpoint_id, checkpoint_ns }: typeof config.configurable) => {
      if (checkpoint_id) {
        const getCommand = new GetCommand({ TableName: this.checkpoints, Key: { thread_id, checkpoint_id } })
        const { Item } = await this.client.send(getCommand)
        return Item
      }

      const queryCommand = new QueryCommand({
        TableName: this.checkpoints,
        KeyConditionExpression: 'thread_id = :thread_id',
        ExpressionAttributeValues: {
          ':thread_id': thread_id,
          ...(checkpoint_ns && { ':checkpoint_ns': checkpoint_ns })
        },
        ...(checkpoint_ns && { FilterExpression: 'checkpoint_ns = :checkpoint_ns' }),
        Limit: 1,
        ScanIndexForward: false
      })

      const { Items } = await this.client.send(queryCommand)

      return Items?.[0]
    }

    const item = await getItem(config.configurable)
    if (!item) {
      return undefined
    }

    const checkpoint = await this.serde.loadsTyped(item.type, item.checkpoint)
    const metadata = await this.serde.loadsTyped(item.type, item.metadata)
    const threadCheckpointNS = [item.thread_id, item.checkpoint_id, item.checkpoint_ns].join(this.separator)

    const pendingWrites = []
    const queryCommand = new QueryCommand({
      TableName: this.checkpointWrites,
      KeyConditionExpression: 'thread_id_checkpoint_id_checkpoint_ns = :thread_id_checkpoint_id_checkpoint_ns',
      ExpressionAttributeValues: { ':thread_id_checkpoint_id_checkpoint_ns': threadCheckpointNS }
    })

    const { Items } = await this.client.send(queryCommand)

    for (const writeItem of Items ?? []) {
      const taskId = writeItem.task_index.split(this.separator)[0]
      const value = await this.serde.loadsTyped(writeItem.type, writeItem.value)
      pendingWrites.push([taskId, writeItem.channel, value])
    }

    return {
      config: {
        configurable: {
          thread_id: item.thread_id,
          checkpoint_ns: item.checkpoint_ns,
          checkpoint_id: item.checkpoint_id
        }
      },
      checkpoint,
      metadata,
      parentConfig: item.parent_checkpoint_id
        ? {
            configurable: {
              thread_id: item.thread_id,
              checkpoint_ns: item.checkpoint_ns,
              checkpoint_id: item.parent_checkpoint_id
            }
          }
        : undefined,
      pendingWrites
    }
  }

  async *list(config: RunnableConfig, options: { limit?: number; before?: RunnableConfig }) {
    const { limit, before } = options ?? {}
    const thread_id = config.configurable?.thread_id
    const expressionAttributeValues = { ':thread_id': thread_id }
    let keyConditionExpression = 'thread_id = :thread_id'

    if (before?.configurable?.checkpoint_id) {
      keyConditionExpression += ' AND checkpoint_id < :before_checkpoint_id'
      expressionAttributeValues[':beforeCheckpointId'] = before.configurable.checkpoint_id
    }

    const queryCommand = new QueryCommand({
      TableName: this.checkpoints,
      KeyConditionExpression: keyConditionExpression,
      ExpressionAttributeValues: expressionAttributeValues,
      Limit: limit,
      ScanIndexForward: false
    })

    const { Items } = await this.client.send(queryCommand)

    for (const item of Items) {
      const checkpoint = await this.serde.loadsTyped(item.type, item.checkpoint)
      const metadata = await this.serde.loadsTyped(item.type, item.metadata)

      yield {
        config: {
          configurable: {
            thread_id: item.thread_id,
            checkpoint_ns: item.checkpoint_ns,
            checkpoint_id: item.checkpoint_id
          }
        },
        checkpoint,
        metadata,
        parentConfig: item.parent_checkpoint_id
          ? {
              configurable: {
                thread_id: item.thread_id,
                checkpoint_ns: item.checkpoint_ns,
                checkpoint_id: item.parent_checkpoint_id
              }
            }
          : undefined
      }
    }
  }

  async put(config: RunnableConfig, checkpoint: Checkpoint, metadata: CheckpointMetadata) {
    const { thread_id, checkpoint_ns } = config.configurable
    const [checkpointType, serializedCheckpoint] = this.serde.dumpsTyped(checkpoint)
    const [metadataType, serializedMetadata] = this.serde.dumpsTyped(metadata)

    if (checkpointType !== metadataType) {
      throw new Error('Failed to serialize checkpoint and metadata to the same type.')
    }

    const putCommand = new PutCommand({
      TableName: this.checkpoints,
      Item: {
        thread_id,
        checkpoint_ns,
        checkpoint_id: checkpoint.id,
        parent_checkpoint_id: config.configurable?.checkpoint_id,
        type: checkpointType,
        checkpoint: serializedCheckpoint,
        metadata: serializedMetadata
      }
    })

    await this.client.send(putCommand)

    return { configurable: { thread_id, checkpoint_ns, checkpoint_id: checkpoint.id } }
  }

  async putWrites(config: RunnableConfig, writes: PendingWrite[], taskId: string) {
    const { thread_id, checkpoint_ns, checkpoint_id } = config.configurable

    if (!checkpoint_id) {
      throw new Error('Missing checkpoint_id')
    }

    const pendingWriteItems = writes.map(([writeChannel, writeType], index) => {
      const [dumpedType, serializedValue] = this.serde.dumpsTyped(writeType)
      return {
        PutRequest: {
          Item: {
            thread_id_checkpoint_id_checkpoint_ns: this.getWritePk(thread_id, checkpoint_id, checkpoint_ns),
            task_index: this.getWriteSk(taskId, index),
            channel: writeChannel,
            type: dumpedType,
            valu: serializedValue
          }
        }
      }
    })

    const batches = []
    for (let i = 0; i < pendingWriteItems.length; i += 25) {
      batches.push(pendingWriteItems.slice(i, i + 25))
    }

    const requests = batches.map((batch) => {
      const batchWriteCommand = new BatchWriteCommand({ RequestItems: { [this.checkpointWrites]: batch } })
      return this.client.send(batchWriteCommand)
    })

    await Promise.all(requests)
  }

  getWritePk(thread_id: string, checkpoint_id: string, checkpoint_ns: string) {
    return [thread_id, checkpoint_id, checkpoint_ns].join(this.separator)
  }

  getWriteSk(taskId: string, index: number) {
    return [taskId, index].join(this.separator)
  }
}

/**
 * Create a new instance of the DynamoDBSaver.
 */
export const createDynamoDBSaver = () => new DynamoDBSaver({ clientConfig: { region: process.env.AWS_REGION } })

/**
 * Get chat history within a specific number of days.
 *
 * @param {string} groupId - The chat group ID.
 * @param {number} [days] - Optional number of days to get chat history.
 */
export const getMessages = async (groupId: string, days?: number) => {
  try {
    const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
    const queryCommand = new QueryCommand({
      TableName: 'Message',
      KeyConditionExpression: 'groupId = :groupId' + (days && ' AND createdAt BETWEEN :start AND :end'),
      ExpressionAttributeValues: {
        ':groupId': groupId,
        ...(days && { ':start': Date.now() - days * 24 * 60 * 60 * 1000, ':end': Date.now() })
      },
      ScanIndexForward: true
    })

    const { Items } = await client.send(queryCommand)

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
 * Store a message to a chat group. The createdAt field will be automatically generated.
 *
 * @param {Object} message - The message to store.
 * @param {string} [message.groupId] - The chat group ID.
 * @param {string} [message.content] - The message content.
 */
export const storeMessage = async (message: Omit<Message, 'createdAt'>) => {
  try {
    const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
    const putCommand = new PutCommand({ TableName: 'Message', Item: { ...message, createdAt: Date.now() } })
    return client.send(putCommand)
  } catch (error) {
    logger.error(error)
    throw error
  }
}

/**
 * Clear all messages in a chat group.
 *
 * @param {string} groupId - The group Id used to find all messages to delete.
 */
export const clearMessages = async (groupId: string) => {
  try {
    const messages = await getMessages(groupId)
    const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
    return Promise.all(
      messages.map(({ createdAt }) => {
        return client.send(new DeleteCommand({ TableName: 'Message', Key: { groupId, createdAt } }))
      })
    )
  } catch (error) {
    logger.error(error)
    throw error
  }
}

/**
 * Get the configuration of a chat group.
 *
 * @param {string} groupId - The chat group ID used to get the configuration.
 */
export const getConfiguration = async (groupId: string) => {
  try {
    const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
    const queryCommand = new QueryCommand({
      TableName: 'ChatConfiguration',
      KeyConditionExpression: 'groupId = :groupId',
      ExpressionAttributeValues: { ':groupId': groupId }
    })

    const { Items } = await client.send(queryCommand)

    return Items?.length ? (Items[0] as Configuration) : undefined
  } catch (error) {
    if (error.name === 'ResourceNotFoundException') {
      return undefined
    }
    logger.error(error)
    throw error
  }
}

/**
 * Set the configuration of a chat group.
 *
 * @param {Object} configuration - The configuration to set.
 * @param {string} configuration.groupId - The chat group ID.
 * @param {string} configuration.chatMode - The chat mode.
 * @param {string} configuration.modelName - The model name.
 */
export const setConfiguration = async (configuration: Configuration) => {
  try {
    const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }))
    const putCommand = new PutCommand({ TableName: 'ChatConfiguration', Item: configuration })
    return client.send(putCommand)
  } catch (error) {
    logger.error(error)
    throw error
  }
}
