import { Document } from '@langchain/core/documents'
import { AIMessage, HumanMessage } from '@langchain/core/messages'
import { StringOutputParser } from '@langchain/core/output_parsers'
import { PromptTemplate } from '@langchain/core/prompts'
import { type RunnableConfig, RunnableSequence } from '@langchain/core/runnables'

import { Annotation, Send, StateGraph } from '@langchain/langgraph'

import { ChatOpenAI } from '@langchain/openai'
import { collapseDocs, splitListOfDocs } from 'langchain/chains/combine_documents/reduce'

import { MAP_PROMPT, REDUCE_PROMPT } from '../../prompts'
import { getMessages } from '../../services/dynamoDB'

interface OverallState {
  chatHistory: AIMessage[]
  collapsedSummaries: Document[]
  messages: AIMessage[]
  summaries: AIMessage[]
}

interface SummarizationState {
  message: AIMessage
}

const countTokens = async (documents: Document[], modelName: string = 'gpt-4o-mini') => {
  const openAI = new ChatOpenAI({ modelName })
  let sum = 0

  for (const document of documents) {
    sum += await openAI.getNumTokens(document.pageContent)
  }

  return sum
}

const readChatHistory = async (_: SummarizationState, { configurable }: RunnableConfig) => {
  const thread = (configurable?.thread_id ?? '') as string
  const messages = await getMessages(thread, 1)
  return { chatHistory: messages.slice(-100).map(({ content }) => new HumanMessage(content)) }
}

const mapSummaries = ({ chatHistory }: OverallState) => {
  return chatHistory.map((message) => new Send('generateSummary', { message }))
}

const generateSummary = async ({ message }: SummarizationState, { configurable }: RunnableConfig) => {
  const modelName = (configurable?.modelName ?? 'gpt-4o-mini') as string
  const chain = RunnableSequence.from([
    new PromptTemplate({ template: MAP_PROMPT, inputVariables: ['context', 'requirements'] }),
    new ChatOpenAI({ modelName }),
    new StringOutputParser()
  ])
  const requirements = (configurable?.question ?? '') as string

  const response = await chain.invoke({ context: message.content.toString(), requirements })

  return { summaries: [new AIMessage(response)] }
}

const collectSummaries = ({ summaries }: OverallState) => {
  return {
    collapsedSummaries: summaries.map(({ content }) => new Document({ pageContent: content.toString() }))
  }
}

const collapseSummaries = async (state: OverallState, { configurable }: RunnableConfig) => {
  const modelName = (configurable?.modelName ?? 'gpt-4o-mini') as string
  const chain = RunnableSequence.from([
    new PromptTemplate({ template: REDUCE_PROMPT, inputVariables: ['docs', 'requirements'] }),
    new ChatOpenAI({ modelName }),
    new StringOutputParser()
  ])
  const requirements = (configurable?.question ?? '') as string

  const docLists = splitListOfDocs(state.collapsedSummaries, countTokens, 1000)
  const summaries = await Promise.all(
    docLists.map((docList) => collapseDocs(docList, (docs) => chain.invoke({ docs, requirements })))
  )

  return { collapsedSummaries: summaries }
}

const shouldCollapse = async ({ collapsedSummaries }: OverallState) => {
  const tokens = await countTokens(collapsedSummaries)

  if (tokens < 1000) {
    return 'collapseSummaries'
  }

  return 'generateFinalSummary'
}

const generateFinalSummary = async (state: OverallState, { configurable }: RunnableConfig) => {
  const modelName = (configurable?.modelName ?? 'gpt-4o-mini') as string
  const chain = RunnableSequence.from([
    new PromptTemplate({ template: REDUCE_PROMPT, inputVariables: ['docs', 'requirements'] }),
    new ChatOpenAI({ modelName, temperature: 0 }),
    new StringOutputParser()
  ])
  const requirements = (configurable?.question ?? '') as string

  const finalSummary = await chain.invoke({ docs: state.collapsedSummaries, requirements })

  return { messages: [new AIMessage(finalSummary)] }
}

/**
 * Get a summarization graph.
 */
export const summarizationGraph = () => {
  const annotation = Annotation.Root({
    chatHistory: Annotation<AIMessage[]>({ reducer: (x, y) => x.concat(y) }),
    collapsedSummaries: Annotation<Document[]>({ reducer: (x, y) => x.concat(y) }),
    messages: Annotation<AIMessage[]>({ reducer: (x, y) => x.concat(y) }),
    summaries: Annotation<AIMessage[]>({ reducer: (x, y) => x.concat(y) })
  })

  const graph = new StateGraph(annotation)
    .addNode('readChatHistory', readChatHistory)
    .addNode('generateSummary', generateSummary)
    .addNode('collectSummaries', collectSummaries)
    .addNode('generateFinalSummary', generateFinalSummary)
    .addNode('collapseSummaries', collapseSummaries)
    .addEdge('__start__', 'readChatHistory')
    .addConditionalEdges('readChatHistory', mapSummaries, ['generateSummary'])
    .addEdge('generateSummary', 'collectSummaries')
    .addConditionalEdges('collectSummaries', shouldCollapse, ['collapseSummaries', 'generateFinalSummary'])
    .addConditionalEdges('collapseSummaries', shouldCollapse, ['collapseSummaries', 'generateFinalSummary'])
    .addEdge('generateFinalSummary', '__end__')

  return graph
}
