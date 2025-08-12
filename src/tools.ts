import type { DynamicStructuredTool } from '@langchain/core/tools'
import type { AppConfig } from './types'

import { Document } from '@langchain/core/documents'
import { HumanMessage, SystemMessage, ToolMessage } from '@langchain/core/messages'
import { tool } from '@langchain/core/tools'
import { Command } from '@langchain/langgraph'
import { z } from 'zod'

import * as prompts from './prompts'

export const tools = {
  websearch: tool(
    async ({ question, timeRange }, { configurable, toolCall }) => {
      const tavily = configurable['search'] as AppConfig['search']

      const answer = await tavily.search(question, timeRange)
      return new Command({
        goto: 'handleMessages',
        update: { messages: [new ToolMessage({ content: answer, tool_call_id: toolCall.id })] }
      })
    },
    {
      name: 'websearch',
      description: `當用戶的問題需要取得以下資訊時，使用這個工具:
        - 即時資訊
        - 特定時間範圍
        - 特定領域資訊
        - 特定主題資訊
        - 特定事件資訊
        - 特定地點資訊
      `,
      schema: z.object({
        question: z.string().describe('要搜尋的問題或主題。'),
        timeRange: z.enum(['day', 'week', 'month', 'year']).describe('要搜尋的時間範圍。')
      })
    }
  ),

  summary: tool(
    async (_, { configurable, toolCall }) => {
      const { ai, square } = configurable as AppConfig
      const { content } = await ai.chat([new SystemMessage(prompts.SUMMARIZATION_PROMPT), ...square.conversation])
      return new Command({
        goto: 'handleMessages',
        update: { messages: [new ToolMessage({ content, tool_call_id: toolCall.id })] }
      })
    },
    {
      name: 'summary',
      description: `當用戶的問題是關於生成對話的摘要或總結時，使用這個工具。`,
      schema: z.object({})
    }
  ),

  chatHistory: tool(
    async ({ question }, { configurable, toolCall }) => {
      const { ai, square } = configurable as AppConfig

      const retriever = square.vectorStore.asRetriever()
      const documents = await retriever.invoke(question)
      const context = documents.map((doc) => new HumanMessage(doc.pageContent))

      const { content } = await ai.chat([
        new SystemMessage(prompts.DO_RETRIEVAL),
        ...context,
        new HumanMessage(question)
      ])

      return new Command({
        goto: 'handleMessages',
        update: { messages: [new ToolMessage({ content, tool_call_id: toolCall.id })] }
      })
    },
    {
      name: 'chatHistory',
      description: `當用戶問你記不記得特定事情時，使用這個工具來檢索聊天記錄。`,
      schema: z.object({
        question: z.string().describe('要檢索的問題或主題。')
      })
    }
  ),

  updateChatHistory: tool(
    async ({ content, target }, { configurable, toolCall }) => {
      const { square } = configurable as AppConfig
      await square.vectorStore.addDocuments([new Document({ id: target, pageContent: content })])
      return new Command({
        goto: 'handleMessages',
        update: {
          reaction: 2,
          messages: [new ToolMessage({ content: '已記住', tool_call_id: toolCall.id })]
        }
      })
    },
    {
      name: 'updateChatHistory',
      description: '當用戶的意圖包含要求你記住特定事情時，必須使用這個工具來記住。',
      schema: z.object({
        content: z.string().describe('要記住的事情的內容。'),
        target: z.string().describe('要記住事情的人。如果沒有指定，則會記住目前正在說話的人。')
      })
    }
  ),

  react: tool(
    async ({ reaction, reason }, { toolCall }) => {
      return new Command({
        goto: 'handleMessages',
        update: {
          reaction: Number(reaction),
          messages: [new ToolMessage({ content: reason, tool_call_id: toolCall.id })]
        }
      })
    },
    {
      name: 'react',
      description: `偶爾使用這個工具來回應用戶的訊息。
      選擇適合的表情符號(reaction code)來回應用戶的訊息:
        - 2: NICE (你同意對方的說法，或覺得對方說的很棒)
        - 3: LOVE (對方的說法讓你感到溫暖)
        - 4: FUN (對方的說法讓你感到有趣)
        - 5: ADMIRE (對方的說法讓你感到佩服)
        - 6: SAD (你對對方的說法感到抱歉)
        - 7: OMG (對方的說法讓你感到驚訝)
      `,
      schema: z.object({
        reaction: z.enum(['2', '3', '4', '5', '6', '7']).describe('表情符號(reaction code)'),
        reason: z.string().describe('選擇表情符號的原因')
      })
    }
  )
} as unknown as { [key: string]: DynamicStructuredTool }
