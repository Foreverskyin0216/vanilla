import { TavilySearchResults } from '@langchain/community/tools/tavily_search'
import { tool } from '@langchain/core/tools'
import { z } from 'zod'
import { retrieveInfoFromWebPage } from './ai'
import { clearMessages, clearThread } from './dynamoDB'

/**
 * Tools for searching and retrieving information from the web
 */
export const toolkit = [
  tool(
    async ({ question }) => {
      const result = JSON.parse(await new TavilySearchResults({ maxResults: 1 }).invoke(question))
      return 'Answer: ' + (await retrieveInfoFromWebPage(result[0].url, question))
    },
    {
      name: 'DuckDuckGoSearch',
      description: '當用戶想要任何資訊時，使用此工具來搜索資訊',
      schema: z.object({ question: z.string().describe('用戶的問題') })
    }
  ),

  tool(
    async (_, { configurable }) => {
      const thread_id = configurable.thread_id
      await clearMessages(thread_id)
      await clearThread(thread_id)
      return '已經清除了所有訊息'
    },
    {
      name: 'EraseMemory',
      description: '用於刪除記憶',
      schema: z.object({})
    }
  )
]
