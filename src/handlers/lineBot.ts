import { type TextEventMessage, type WebhookEvent } from '@line/bot-sdk'
import { type Context, type SNSEvent } from 'aws-lambda'

import { HumanMessage } from '@langchain/core/messages'
import { chatGraph } from '../graphs/chat'

import { clearMessages, getConfiguration, setConfiguration, storeMessage } from '../services/dynamoDB'
import { reply, getProfile } from '../services/messagingAPI'

import { logger } from '../utils/logger'
import { parseDebugCommand } from '../utils/parser'

const NAME = '香草'

const chat = async (groupId: string, question: string) => {
  const message = new HumanMessage(question)
  let configuration = await getConfiguration(groupId)

  if (!configuration) {
    const defaultConfiguration = { groupId, chatMode: 'normal', modelName: 'gpt-4o-mini' }
    await setConfiguration(defaultConfiguration)
    configuration = defaultConfiguration
  }

  const { conversation } = await chatGraph().invoke(
    { conversation: [message], messages: [message] },
    {
      configurable: {
        chatMode: configuration.chatMode || 'normal',
        modelName: configuration.modelName || 'gpt-4o-mini',
        question,
        thread_id: groupId
      }
    }
  )
  const response = conversation[conversation.length - 1].content.toString()

  return response.replace(`${NAME}：`, '') as string
}

const debug = async (groupId: string, replyToken: string, message: TextEventMessage) => {
  const { command, params, error } = parseDebugCommand(message.text)
  if (error) {
    await reply(replyToken, [{ type: 'text', text: error, quoteToken: message.quoteToken }])
    return
  }

  switch (command) {
    case 'info': {
      let configuration = await getConfiguration(groupId)
      if (!configuration) {
        const defaultConfiguration = { groupId, chatMode: 'normal', modelName: 'gpt-4o-mini' }
        await setConfiguration(defaultConfiguration)
        configuration = defaultConfiguration
      }
      const text = Object.entries(configuration)
        .map(([key, value]) => `${key}：${value}`)
        .join('\n')
      await reply(replyToken, [{ type: 'text', text, quoteToken: message.quoteToken }])
      break
    }

    case 'configure': {
      const chatMode = params['chat-mode'] || 'normal'
      const modelName = params['model'] || 'gpt-4o-mini'
      await setConfiguration({ groupId, chatMode, modelName })
      await reply(replyToken, [{ type: 'text', text: 'OK', quoteToken: message.quoteToken }])
      break
    }

    case 'cleanup': {
      await clearMessages(groupId)
      await reply(replyToken, [{ type: 'text', text: 'OK', quoteToken: message.quoteToken }])
      break
    }
  }
}

export const lineBot = async (event: SNSEvent, context: Context) => {
  logger.addContext(context)
  const { events } = JSON.parse(event.Records[0].Sns.Message)

  for (const { source, ...event } of events as WebhookEvent[]) {
    if (event.type !== 'message' || event.message.type !== 'text' || source.type !== 'group') {
      continue
    }

    const { replyToken, message } = event
    const { displayName } = await getProfile(source.groupId, source.userId)
    const question = message.text.replaceAll(`@${NAME}`, '').trim()
    await storeMessage({ groupId: source.groupId, content: `${displayName}：${question}` })

    if (message.text.includes(`@${NAME}`)) {
      if (question.includes('debug')) {
        await debug(source.groupId, replyToken, message)
      }

      const response = await chat(source.groupId, `${displayName}：${question}`)

      return reply(replyToken, [{ type: 'text', text: response, quoteToken: message.quoteToken }])
    }
  }

  return 'Do nothing'
}
