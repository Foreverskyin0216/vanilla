import type { BaseMessage } from '@langchain/core/messages'
import type { AI } from './ai'
import type { Search } from './search'

export type AppConfig = {
  ai: AI
  botName: string
  search: Search
  square: SquareStatus
}

export type BotStatus = {
  [key: string]: SquareStatus
}

export type MemberStatus = {
  name: string
  messages: Message[]
}

export type Message = {
  id: string
  content: BaseMessage
}

export type SquareStatus = {
  botId: string
  conversation: BaseMessage[]
  members: { [key: string]: MemberStatus }
}
