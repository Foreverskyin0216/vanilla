import type { Document } from '@langchain/core/documents'
import type { BaseMessage } from '@langchain/core/messages'
import type { DynamicStructuredTool } from '@langchain/core/tools'

import { CheerioWebBaseLoader } from '@langchain/community/document_loaders/web/cheerio'
import { StringOutputParser } from '@langchain/core/output_parsers'
import { PromptTemplate } from '@langchain/core/prompts'
import { RunnableSequence } from '@langchain/core/runnables'
import { ChatOpenAI, OpenAIEmbeddings } from '@langchain/openai'

import { createStuffDocumentsChain } from 'langchain/chains/combine_documents'
import { RecursiveCharacterTextSplitter } from 'langchain/text_splitter'
import { MemoryVectorStore } from 'langchain/vectorstores/memory'
import { OpenAI } from 'openai'
import { setTimeout } from 'timers/promises'
import { z } from 'zod'

import { botPersonality, classification, mapDocuments, reduceDocuments, retrieve } from './prompts'

export const createThread = async () => new OpenAI().beta.threads.create()

export const classify = async (question: string) => {
  const openai = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 })
  const schema = z.object({ intent: z.enum(['summarization', 'tools', 'chat']) })
  return openai.withStructuredOutput(schema).invoke([
    { role: 'system', content: classification },
    { role: 'user', content: question }
  ])
}

export const chat = async (threadId: string, humanMessage: BaseMessage, aiMessage?: BaseMessage) => {
  const { beta: openai } = new OpenAI()
  const question = humanMessage.content.toString()
  const answer = aiMessage?.content?.toString()
  const assistant = await openai.assistants.create({
    instructions: botPersonality,
    model: 'gpt-4o-mini',
    tools: [{ type: 'code_interpreter' }]
  })
  if (answer)
    await openai.threads.messages.create(threadId, {
      content: '剛剛我問了：「' + question + '」，現在我得到答案了，用你的風格描述一次答案：「' + answer + '」',
      role: 'user'
    })
  else await openai.threads.messages.create(threadId, { content: question, role: 'user' })
  const run = await openai.threads.runs.create(threadId, { assistant_id: assistant.id })
  const startTime = Date.now()
  let completed = false

  while (!completed || Date.now() - startTime > 60000) {
    completed = (await openai.threads.runs.retrieve(threadId, run.id)).status === 'completed'
    await setTimeout(500)
  }

  const messages = await openai.threads.messages.list(threadId, { limit: 1 })
  const reply = messages.data[0].content[0] as { text: { value: string } }

  return reply.text.value
}

export const useTools = async (tools: DynamicStructuredTool[], messages: BaseMessage[]) =>
  new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 }).bindTools(tools).invoke(messages)

export const retrieveInfoFromWebPage = async (link: string, question: string) => {
  const loader = new CheerioWebBaseLoader(link)
  const docs = await loader.load()
  const splitter = new RecursiveCharacterTextSplitter({ chunkSize: 1000 })
  const store = await MemoryVectorStore.fromDocuments(
    await splitter.splitDocuments(docs),
    new OpenAIEmbeddings({ model: 'text-embedding-3-small' })
  )

  const chain = await createStuffDocumentsChain({
    llm: new ChatOpenAI({ modelName: 'gpt-4o-mini' }),
    outputParser: new StringOutputParser(),
    prompt: new PromptTemplate({ template: retrieve, inputVariables: ['question', 'context'] })
  })

  return chain.invoke({ question, context: await store.asRetriever().invoke(question) })
}

export const summarize = async (context: string, requirements: BaseMessage) =>
  RunnableSequence.from([
    new PromptTemplate({ template: mapDocuments, inputVariables: ['context', 'requirements'] }),
    new ChatOpenAI({ modelName: 'gpt-4o-mini' }),
    new StringOutputParser()
  ]).invoke({ context, requirements })

export const collapse = async (docs: Document[], requirements: BaseMessage) =>
  RunnableSequence.from([
    new PromptTemplate({ template: reduceDocuments, inputVariables: ['docs', 'requirements'] }),
    new ChatOpenAI({ modelName: 'gpt-4o-mini' }),
    new StringOutputParser()
  ]).invoke({ docs, requirements })
