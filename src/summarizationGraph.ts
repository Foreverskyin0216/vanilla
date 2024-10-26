import type { LangGraphRunnableConfig as Config, MemorySaver } from '@langchain/langgraph'

import { Document } from '@langchain/core/documents'
import { AIMessage, HumanMessage } from '@langchain/core/messages'
import { Annotation, Send, StateGraph } from '@langchain/langgraph'
import { summarize, collapse } from './ai'
import { getMessages } from './dynamoDB'

interface MessageState {
  requirements: HumanMessage
  message: AIMessage
}

const OverallState = Annotation.Root({
  collapsedSummaries: Annotation<Document[]>({ reducer: (x, y) => x.concat(y) }),
  messages: Annotation<AIMessage[]>({ reducer: (x, y) => x.concat(y) }),
  summaries: Annotation<AIMessage[]>({ reducer: (x, y) => x.concat(y) })
})

const mapSummaries = async ({ messages }: typeof OverallState.State, { configurable }: Config) => {
  const chatHistory = await getMessages(configurable.thread_id)
  return chatHistory.slice(-100).map((message) => new Send('generateSummary', { message, requirements: messages[0] }))
}

const generateSummary = async ({ message, requirements }: MessageState) => {
  const summary = await summarize(message.content.toString(), requirements)
  return { summaries: [new AIMessage(summary)] }
}

const collectSummaries = ({ summaries }: typeof OverallState.State) => {
  return { collapsedSummaries: summaries.map(({ content }) => new Document({ pageContent: content.toString() })) }
}

const generateFinalSummary = async ({ collapsedSummaries, messages }: typeof OverallState.State) => {
  const requirements = messages.findLast((message) => message.getType() === 'human')
  const finalSummary = await collapse(collapsedSummaries, requirements)
  return { messages: [new AIMessage(finalSummary)] }
}

export const summarizationGraph = (checkpointer: MemorySaver) =>
  new StateGraph(OverallState)
    .addNode('generateSummary', generateSummary)
    .addNode('collectSummaries', collectSummaries)
    .addNode('generateFinalSummary', generateFinalSummary)
    .addConditionalEdges('__start__', mapSummaries, ['generateSummary'])
    .addEdge('generateSummary', 'collectSummaries')
    .addEdge('collectSummaries', 'generateFinalSummary')
    .addEdge('generateFinalSummary', '__end__')
    .compile({ checkpointer })
