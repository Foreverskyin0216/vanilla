import type { BaseMessage } from '@langchain/core/messages'
import type { LangGraphRunnableConfig as Config, MemorySaver } from '@langchain/langgraph'

import { AIMessage, RemoveMessage } from '@langchain/core/messages'
import { Annotation, StateGraph, messagesStateReducer } from '@langchain/langgraph'
import { ToolNode } from '@langchain/langgraph/prebuilt'

import { classify, chat, useTools } from './ai'
import { toolkit } from './tools'
import { summarizationGraph } from './summarizationGraph'

const ChatState = Annotation.Root({
  messages: Annotation<BaseMessage[]>({ reducer: messagesStateReducer }),
  response: Annotation<string>,
  reference: Annotation<string>
})

export const shouldInvoke = async ({ messages }: typeof ChatState.State) => {
  const { intent } = await classify(messages[0].content.toString())
  return intent
}

export const toolsNode = async ({ messages }: typeof ChatState.State) => {
  return { messages: [await useTools(toolkit, messages)] }
}

export const shouldUseTools = ({ messages }: typeof ChatState.State) => {
  const message = messages[messages.length - 1] as AIMessage
  return message?.tool_calls?.length > 0 ? 'toolkit' : 'chat'
}

export const chatNode = async ({ messages }: typeof ChatState.State, { configurable }: Config) => {
  const question = messages[0]
  const response = messages[messages.length - 1].getType() === 'ai' ? messages[messages.length - 1] : undefined
  const result = await chat(configurable.conversation_id, question, response)
  return { messages: [], response: result, reference: process.env.REFERENCED_URL }
}

export const cleanupNode = ({ messages }: typeof ChatState.State) => {
  delete process.env.REFERENCED_URL
  return { messages: messages.map(({ id }) => new RemoveMessage({ id })) }
}

export const chatGraph = (checkpointer: MemorySaver) =>
  new StateGraph(ChatState)
    .addNode('summarization', summarizationGraph(checkpointer))
    .addNode('tools', toolsNode)
    .addNode('chat', chatNode)
    .addNode('cleanup', cleanupNode)
    .addNode('toolkit', new ToolNode(toolkit))
    .addConditionalEdges('__start__', shouldInvoke, ['summarization', 'tools', 'chat'])
    .addEdge('summarization', 'chat')
    .addConditionalEdges('tools', shouldUseTools, ['toolkit', 'chat'])
    .addEdge('toolkit', 'tools')
    .addEdge('chat', 'cleanup')
    .addEdge('cleanup', '__end__')
    .compile({ checkpointer })
