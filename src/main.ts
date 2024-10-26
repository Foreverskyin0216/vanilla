process.env.AWS_REGION = process.env.AWS_REGION || 'ap-southeast-2'
process.env.MODEL_NAME = process.env.MODEL_NAME || 'gpt-4o-mini'

import { Client } from '@evex/linejs'

import { HumanMessage } from '@langchain/core/messages'
import { MemorySaver } from '@langchain/langgraph'
import { chatGraph } from './graphs/chat'

import { storeMessage, clearMessages } from './services/dynamoDB'
import { getParameter, setParameter } from './services/ssm'

import { logger } from './utils/logger'
import { parseDebugCommand } from './utils/parser'

// Workaround for https://github.com/evex-dev/linejs/issues/45
process.on('uncaughtException', (error) => {
  if (error.name === 'InputBufferUnderrunError') {
    return logger.error('InputBufferUnderrunError')
  }
  throw error
})

class ChatBot {
  client: Client
  checkpointer: MemorySaver
  name: string = '香草'
  mode: string = 'normal'

  constructor(checkpointer: MemorySaver) {
    this.client = new Client()
    this.checkpointer = checkpointer

    this.client.on('ready', async () => {
      const refreshToken = this.client.storage.get('refreshToken') as string
      await setParameter('/vanilla/line/refreshToken', refreshToken)

      const openaiApiKey = await getParameter('/vanilla/openai/apiKey')
      process.env.OPENAI_API_KEY = openaiApiKey

      logger.info('Logged in')
    })

    this.client.on('update:authtoken', async (authToken) => {
      await setParameter('/vanilla/line/authToken', authToken)
    })

    this.client.on(
      'square:message',
      async ({ author, content, contentMetadata, contentType, squareChatMid, react, reply }) => {
        try {
          if (contentType === 'NONE' && content) {
            const user = await author.displayName
            const question = content.replaceAll(`@${this.name}`, '').trim()
            await storeMessage({ groupId: squareChatMid, content: `${user}：${question}` })

            if (contentMetadata?.MENTION && content.includes(`@${this.name}`)) {
              if (question.includes('debug')) {
                const state = await this.debug(squareChatMid, question)
                return Promise.all(state === 'OK' ? [react(2)] : [react(6), reply(state)])
              }

              const response = await this.chat(squareChatMid, `${user}：${question}`)

              return reply(response)
            }
          }

          return 'Do nothing'
        } catch (err) {
          const message = JSON.stringify({ error: err.name }, null, 2)
          return Promise.all([react(6), reply(message)])
        }
      }
    )
  }

  private async debug(squareChatMid: string, question: string) {
    const { command, params, error } = parseDebugCommand(question)
    switch (command) {
      case 'info': {
        const text = [`聊天模式：${this.mode}`, `語言模型：${process.env.MODEL_NAME}`].join('\n')
        await this.client.sendSquareMessage({ squareChatMid, contentType: 0, text })
        break
      }

      case 'configure': {
        this.mode = params['chat-mode'] || 'normal'
        process.env.MODEL_NAME = params['model'] || process.env.MODEL_NAME
        break
      }

      case 'graph': {
        const expand = params?.expand === 'true'
        const graph = chatGraph().getGraph({ xray: expand })
        const image = await graph.drawMermaidPng({ withStyles: !expand })
        await this.client.uploadObjTalk(squareChatMid, 'image', image)
        break
      }

      case 'cleanup': {
        this.checkpointer = new MemorySaver()
        await clearMessages(squareChatMid)
        break
      }

      case 'revoke': {
        await this.client.tryRefreshToken()
        await this.client.logout()
        await this.login()
        break
      }
    }

    return error ? error : 'OK'
  }

  private async chat(squareChatMid: string, question: string) {
    const message = new HumanMessage(question)

    const { conversation } = await chatGraph(this.checkpointer).invoke(
      { conversation: [message], messages: [message] },
      {
        configurable: { thread_id: squareChatMid, question, chatMode: this.mode }
      }
    )
    const response = conversation[conversation.length - 1].content.toString()

    return response.replace(`${this.name}：`, '') as string
  }

  public async login() {
    logger.info('Logging in...')
    const authToken = await getParameter('/vanilla/line/authToken')
    const refreshToken = await getParameter('/vanilla/line/refreshToken')

    if (authToken && refreshToken) {
      this.client.storage.set('refreshToken', refreshToken)
      return this.client.login({ authToken, device: 'DESKTOPMAC', v3: true })
    }

    const email = await getParameter('/vanilla/line/email')
    const password = await getParameter('/vanilla/line/password')

    return this.client.login({ email, password, device: 'DESKTOPMAC', v3: true })
  }
}

;(async () => await new ChatBot(new MemorySaver()).login())()
