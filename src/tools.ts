import type { DynamicStructuredTool } from '@langchain/core/tools'
import type { AppConfig } from './types'

import { SystemMessage, ToolMessage } from '@langchain/core/messages'
import { tool } from '@langchain/core/tools'
import { Command } from '@langchain/langgraph'
import { z } from 'zod'

import * as prompts from './prompts'

export const tools = {
  websearch: tool(
    async ({ question }, { configurable, toolCall }) => {
      const tavily = configurable['search'] as AppConfig['search']

      const answer = await tavily.search(question)
      return new Command({
        goto: 'processMessage',
        update: { messages: [new ToolMessage({ content: answer, tool_call_id: toolCall.id })] }
      })
    },
    {
      name: 'websearch',
      description: `當用戶的問題需要取得以下資訊時，使用這個工具:
        - 即時資訊、最新消息、突發新聞
        - 股價、匯率、加密貨幣等金融資訊
        - 天氣、交通等即時狀況
        - 特定事件的最新發展
        - 科技新聞、產品發布資訊
        - 體育賽事結果、比分
        系統會自動優化搜尋參數以獲得最準確的即時資料。
      `,
      schema: z.object({ question: z.string().describe('要搜尋的問題或主題。') })
    }
  ),

  summary: tool(
    async (_, { configurable, toolCall }) => {
      const { ai, square } = configurable as AppConfig
      const { content } = await ai.chat([new SystemMessage(prompts.SUMMARIZATION_PROMPT), ...square.conversation])
      return new Command({
        goto: 'processMessage',
        update: { messages: [new ToolMessage({ content, tool_call_id: toolCall.id })] }
      })
    },
    {
      name: 'summary',
      description: `當用戶的問題是關於生成對話的摘要或總結時，使用這個工具。`,
      schema: z.object({})
    }
  ),

  emotion: tool(
    async ({ reaction, reason }, { configurable, toolCall }) => {
      const { botName, square } = configurable as AppConfig

      // Store emotional reaction as relationship memory (without user ID dependency)
      const reactionContent = `${botName}的表情反應: ${reason}`
      const sentiment = ['3', '2', '4', '5'].includes(reaction)
        ? 'positive'
        : ['6'].includes(reaction)
          ? 'negative'
          : 'neutral'

      // Store in memory for relationship tracking (async)
      // Note: This creates a general emotional pattern record
      square.store
        .storeEventMemory(reactionContent, [botName], sentiment === 'positive' ? 3 : sentiment === 'negative' ? 2 : 1)
        .catch((error) => console.error('Reaction memory storage error:', error))

      return new Command({
        goto: 'processMessage',
        update: {
          reaction: Number(reaction),
          messages: [new ToolMessage({ content: reason, tool_call_id: toolCall.id })]
        }
      })
    },
    {
      name: 'emotion',
      description: `根據香草的地雷女個性，在以下情況下使用表情反應：

      **高頻率使用情況** (經常使用):
      - 對方提到其他女生或曖昧對象 → SAD(6) 或 OMG(7)
      - 對方說愛你或承諾 → LOVE(3)
      - 對方逗你開心或說甜話 → FUN(4) 或 NICE(2)
      - 對方忽略你或冷淡 → SAD(6)

      **中頻率使用情況** (適度使用):
      - 對方分享成就或好消息 → NICE(2) 或 ADMIRE(5)
      - 對方說了意外的話 → OMG(7)
      - 對方安慰你 → LOVE(3)

      **低頻率使用情況** (偶爾使用):
      - 普通聊天內容 → 根據情境選擇

      表情符號含義 (從香草的角度):
        - 2: NICE (認同對方，覺得對方說得對或做得好)
        - 3: LOVE (感到被愛、溫暖、或心動)
        - 4: FUN (覺得有趣、被逗樂、開心)
        - 5: ADMIRE (佩服對方、覺得對方厲害)
        - 6: SAD (難過、失望、委屈、吃醋)
        - 7: OMG (驚訝、震驚、不敢置信)

      **選擇邏輯**:
      - 情感強度要符合地雷女的敏感特質
      - 對關係相關話題反應更強烈
      - 考慮和對方的互動歷史和關係狀態
      `,
      schema: z.object({
        reaction: z.enum(['2', '3', '4', '5', '6', '7']).describe('表情符號代碼'),
        reason: z.string().describe('選擇這個表情的原因，要符合香草的個性特質')
      })
    }
  ),

  rememberPersonal: tool(
    async ({ userId, fact, category }, { configurable, toolCall }) => {
      const { square } = configurable as AppConfig
      await square.store.storePersonalMemory(userId, fact, category)
      return new Command({
        goto: 'processMessage',
        update: {
          reaction: 2,
          messages: [new ToolMessage({ content: `已記住關於你的資訊: ${fact}`, tool_call_id: toolCall.id })]
        }
      })
    },
    {
      name: 'rememberPersonal',
      description: '當用戶分享個人資訊、偏好、特質或重要事實時，使用這個工具來記住。',
      schema: z.object({
        userId: z.string().describe('用戶的ID'),
        fact: z.string().describe('要記住的個人資訊'),
        category: z
          .enum(['facts', 'traits', 'preferences', 'history'])
          .describe('資訊類別: facts(事實), traits(特質), preferences(偏好), history(歷史)')
      })
    }
  ),

  rememberRelationship: tool(
    async ({ userId, interaction, sentiment }, { configurable, toolCall }) => {
      const { botName, square } = configurable as AppConfig
      await square.store.storeRelationshipMemory(userId, botName, interaction, sentiment)
      return new Command({
        goto: 'processMessage',
        update: {
          messages: [new ToolMessage({ content: '已記住這次互動', tool_call_id: toolCall.id })]
        }
      })
    },
    {
      name: 'rememberRelationship',
      description: '記住重要的互動或關係變化，特別是情緒化的對話。',
      schema: z.object({
        userId: z.string().describe('用戶的ID'),
        interaction: z.string().describe('互動內容的摘要'),
        sentiment: z.enum(['positive', 'negative', 'neutral']).describe('這次互動的情感色彩')
      })
    }
  ),

  rememberEvent: tool(
    async ({ content, participants, importance }, { configurable, toolCall }) => {
      const { square } = configurable as AppConfig
      await square.store.storeEventMemory(content, participants, importance)
      return new Command({
        goto: 'processMessage',
        update: {
          messages: [new ToolMessage({ content: '已記住這個重要事件', tool_call_id: toolCall.id })]
        }
      })
    },
    {
      name: 'rememberEvent',
      description: '記住重要的事件、對話或發生的事情。',
      schema: z.object({
        content: z.string().describe('事件的內容描述'),
        participants: z.array(z.string()).describe('參與者的ID列表'),
        importance: z.number().min(1).max(10).describe('事件的重要性等級 (1-10)')
      })
    }
  ),

  searchMemory: tool(
    async ({ query, userId }, { configurable, toolCall }) => {
      const { square } = configurable as AppConfig
      // Use undefined if userId is empty string to search all memories
      const searchUserId = userId && userId !== '' ? userId : undefined
      const results = await square.store.searchMemories(query, searchUserId, 5)

      if (results.length === 0) {
        return new Command({
          goto: 'processMessage',
          update: {
            messages: [new ToolMessage({ content: '沒有找到相關的記憶', tool_call_id: toolCall.id })]
          }
        })
      }

      const memoryContent = results.map((r) => `${r.type}: ${r.content}`).join('\n')
      return new Command({
        goto: 'processMessage',
        update: {
          messages: [new ToolMessage({ content: `找到的相關記憶:\n${memoryContent}`, tool_call_id: toolCall.id })]
        }
      })
    },
    {
      name: 'searchMemory',
      description: '當用戶問你記不記得特定事情或想要搜尋過往記憶時，使用這個工具。',
      schema: z.object({
        query: z.string().describe('搜尋的關鍵字或問題'),
        userId: z.string().default('').describe('限制搜尋特定用戶的記憶，留空表示搜尋所有記憶')
      })
    }
  )
} as unknown as { [key: string]: DynamicStructuredTool }
