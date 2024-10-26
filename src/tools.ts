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
      try {
        const { content } = await new TavilySearchResults({ maxResults: 1 }).invoke(question)
        const link = JSON.parse(content)[0].url
        process.env.REFERENCED_URL = link
        return 'Answer: ' + (await retrieveInfoFromWebPage(link, question))
      } catch {
        return '這個問題太難了，無法找到答案'
      }
    },
    {
      name: 'DuckDuckGoSearch',
      description: '當用戶想要任何資訊時，使用此工具來搜索資訊',
      schema: z.object({ question: z.string().describe('用戶的問題，如果不夠清晰，再自行添加更詳細的補充用於搜索') })
    }
  ),

  tool(
    async (_, { configurable }) => {
      try {
        const thread_id = configurable.thread_id
        await clearMessages(thread_id)
        await clearThread(thread_id)
        return '已經清除了所有訊息'
      } catch {
        return '無法清除訊息'
      }
    },
    {
      name: 'EraseMemory',
      description: '用於刪除記憶',
      schema: z.object({})
    }
  )
]
