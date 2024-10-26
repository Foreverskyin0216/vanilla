import { CheerioWebBaseLoader } from '@langchain/community/document_loaders/web/cheerio'
import { DuckDuckGoSearch } from '@langchain/community/tools/duckduckgo_search'

import { StringOutputParser } from '@langchain/core/output_parsers'
import { PromptTemplate } from '@langchain/core/prompts'
import { type RunnableConfig } from '@langchain/core/runnables'
import { tool } from '@langchain/core/tools'

import { ChatOpenAI, OpenAIEmbeddings } from '@langchain/openai'

import { createStuffDocumentsChain } from 'langchain/chains/combine_documents'
import { RecursiveCharacterTextSplitter } from 'langchain/text_splitter'
import { MemoryVectorStore } from 'langchain/vectorstores/memory'

import { OpenAI } from 'openai'
import { zodResponseFormat } from 'openai/helpers/zod'

import { z } from 'zod'
import { SEARCH_PROMPT, RETRIEVAL_PROMPT } from '../prompts'

/**
 * Tools for searching and retrieving information from the web
 */
export const toolkit = [
  tool(
    async (_, { configurable }: RunnableConfig) => {
      const modelName = (configurable?.modelName ?? 'gpt-4o-mini') as string
      const question = (configurable?.question ?? '') as string

      const openAI = new OpenAI()
      const completion = await openAI.beta.chat.completions.parse({
        model: modelName,
        temperature: 0,
        messages: [
          { role: 'system', content: SEARCH_PROMPT },
          { role: 'user', content: question }
        ],
        response_format: zodResponseFormat(z.object({ query: z.string() }), 'query')
      })
      const { query } = completion.choices[0].message.parsed

      const search = new DuckDuckGoSearch({ maxResults: 1, searchOptions: { region: 'tw-tzh' } })
      const results = JSON.parse(await search.invoke(query))

      return results?.length > 0 ? `Search result: ${JSON.stringify(results[0])}` : 'Search results not found'
    },
    {
      name: 'DuckDuckGoSearch',
      description: 'Call to search for real-time information from the web',
      schema: z.object({})
    }
  ),

  tool(
    async ({ link }, { configurable }: RunnableConfig) => {
      const modelName = (configurable?.modelName ?? 'gpt-4o-mini') as string
      const question = (configurable?.question ?? '') as string

      const loader = new CheerioWebBaseLoader(link)
      const docs = await loader.load()
      const splitter = new RecursiveCharacterTextSplitter({ chunkSize: 1000 })
      const store = await MemoryVectorStore.fromDocuments(await splitter.splitDocuments(docs), new OpenAIEmbeddings())

      const chain = await createStuffDocumentsChain({
        llm: new ChatOpenAI({ modelName }),
        outputParser: new StringOutputParser(),
        prompt: new PromptTemplate({ template: RETRIEVAL_PROMPT, inputVariables: ['question', 'context'] })
      })

      const retrieved = await store.asRetriever().invoke(question)
      const result = await chain.invoke({ question, context: retrieved })

      return `Answer: ${result}`
    },
    {
      name: 'Retrieval',
      description: 'Call to retrieve information from a specific link',
      schema: z.object({
        link: z.string().describe('Link to retrieve information from')
      })
    }
  )
]
