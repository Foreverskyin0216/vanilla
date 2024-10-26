import type { SquareMessage } from '@evex/linejs'
import type { Device } from '@evex/linejs/base'
import type { AppConfig, BotStatus } from './types'

import { Client } from '@evex/linejs'
import { BaseClient } from '@evex/linejs/base'
import { HumanMessage } from '@langchain/core/messages'
import Queue from 'p-queue'

import { AI } from './ai'
import { Search } from './search'
import { LongTermMemoryManager } from './memory'
import { buildGraph } from './graph'

export class ChatBot {
  private ai: AI
  private app = buildGraph()
  private botName = ''
  private botStatus: BotStatus = {}
  private client: Client
  private queue = new Queue({ concurrency: 1 })
  private search: Search

  constructor(botName: string, device: Device = 'DESKTOPMAC') {
    this.ai = new AI({ model: 'gpt-4.1' })
    this.botName = botName
    this.client = new Client(new BaseClient({ device }))
    this.search = new Search()
  }

  private async _addMember(message: SquareMessage['raw']['message']) {
    const squareChatId = message.to
    const memberId = message.from
    const member = await this._getMember(message)

    if (memberId in this.botStatus[squareChatId].members) {
      this.botStatus[squareChatId].members[memberId].name = member.displayName
      return
    }

    this.botStatus[squareChatId].members[memberId] = { name: member.displayName, messages: [] }

    if (member.displayName === this.botName) {
      this.botStatus[squareChatId].botId = member.squareMemberMid
    }
  }

  private _addMessage(message: SquareMessage['raw']['message']) {
    const squareChatId = message.to
    const memberId = message.from

    const member = this.botStatus[squareChatId].members[memberId].name
    const content = new HumanMessage(`${member}: ${message.text.replaceAll('@' + this.botName, '').trim()}`)

    const conversation = this.botStatus[squareChatId].conversation
    conversation.push(content)
    if (conversation.length > 100) {
      conversation.shift()
    }

    const messages = this.botStatus[squareChatId].members[memberId].messages
    messages.push({ id: message.id, content })
    if (messages.length > 100) {
      messages.shift()
    }
  }

  private async _addSquare(message: SquareMessage['raw']['message']) {
    const squareChatId = message.to
    if (squareChatId in this.botStatus) {
      return
    }

    const store = new LongTermMemoryManager(this.ai, this.botName, `./data/memory-${squareChatId}.json`)
    await store.initialize()

    this.botStatus[squareChatId] = { botId: '', conversation: [], members: {}, store }
  }

  private async _chat(event: SquareMessage) {
    try {
      const message = event.raw.message
      if (message.contentType !== 'NONE') {
        return
      }

      this._addSquare(message)
      await this._addMember(message)
      this._addMessage(message)

      const isBotReply = await event.isMyMessage()
      if (isBotReply) {
        return
      }

      if (!this._isMentioned(message) && !this._isReply(message)) {
        return
      }

      const square = this.botStatus[message.to]
      const userMessage = message.text.replaceAll('@' + this.botName, '').trim()

      const { messages, reaction } = await this.app.invoke(
        {
          messages: square.conversation,
          reaction: [0],
          userName: square.members[message.from].name,
          userMessage: userMessage,
          toolCallCount: 0
        },
        {
          configurable: {
            ai: this.ai,
            botName: this.botName,
            search: this.search,
            square
          } as AppConfig
        }
      )

      if (reaction.length > 1) {
        await event.react(reaction[reaction.length - 1])
      }

      const answer = messages[messages.length - 1].content.toString()
      if (answer) {
        const cleanAnswer = answer.replaceAll(`${this.botName}:`, '').replaceAll(`${this.botName}：`, '').trim()

        await event.reply({
          text: cleanAnswer,
          relatedMessageId: message.id
        })
      }
    } catch (error) {
      console.error(error)
    }
  }

  private async _getMember(message: SquareMessage['raw']['message']) {
    const squareChatId = message.to
    const memberId = message.from

    const chat = await this.client.getSquareChat(squareChatId)
    const members = await chat.getMembers()

    return members.find((member) => member.squareMemberMid === memberId)
  }

  private _isMentioned(message: SquareMessage['raw']['message']) {
    const metadata = message.contentMetadata || {}
    const square = this.botStatus[message.to]

    if (!square.botId) {
      return 'MENTION' in metadata && message.text.includes('@' + this.botName)
    }

    return 'MENTION' in metadata && metadata['MENTION'].includes(square.botId)
  }

  private _isReply(message: SquareMessage['raw']['message']) {
    const relatedMessageId = message.relatedMessageId
    const square = this.botStatus[message.to]

    if (!relatedMessageId || !square || !square.members[square.botId]) {
      return false
    }

    return square.members[square.botId].messages.map((m) => m.id).includes(relatedMessageId)
  }

  public async serve() {
    const login = this.client.base.loginProcess
    await login.withPassword({ email: process.env.LINE_EMAIL, password: process.env.LINE_PASSWORD, v3: true })
    this.client.on('square:message', (event) => this.queue.add(() => this._chat(event))).listen()
  }
}
