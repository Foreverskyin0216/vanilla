import { AIMessage, HumanMessage, RemoveMessage } from '@langchain/core/messages'
import { PromptTemplate } from '@langchain/core/prompts'
import { type RunnableConfig } from '@langchain/core/runnables'

import { Annotation, StateGraph, messagesStateReducer } from '@langchain/langgraph'
import { ToolNode } from '@langchain/langgraph/prebuilt'

import { ChatOpenAI } from '@langchain/openai'
import { OpenAI } from 'openai'
import { zodResponseFormat } from 'openai/helpers/zod'

import { z } from 'zod'

import { ADJUSTMENT_PROMPT, CHAT_PROMPT, CHAT_POSITIVE_PROMPT, CLASSIFICATION_PROMPT } from '../prompts'
import { createDynamoDBSaver } from '../services/dynamoDB'
import { toolkit } from '../tools/searchToolkit'
import { summarizationGraph } from './subgraphs/summarization'

interface ChatState {
  messages: AIMessage[]
  conversation: (AIMessage | HumanMessage)[]
}

const shouldInvoke = async (_: ChatState, { configurable }: RunnableConfig) => {
  const modelName = (configurable?.modelName ?? 'gpt-4o-mini') as string
  const question = (configurable?.question ?? '') as string

  const openAI = new OpenAI()
  const completion = await openAI.beta.chat.completions.parse({
    model: modelName,
    temperature: 0,
    messages: [
      { role: 'system', content: CLASSIFICATION_PROMPT },
      { role: 'user', content: question }
    ],
    response_format: zodResponseFormat(z.object({ intent: z.enum(['summarization', 'search', 'chat']) }), 'intent')
  })
  const { intent } = completion.choices[0].message.parsed

  return intent
}

const searchNode = async ({ messages }: ChatState, { configurable }: RunnableConfig) => {
  const question = (configurable?.question ?? '') as string
  const modelName = (configurable?.modelName ?? 'gpt-4o-mini') as string
  const openAI = new ChatOpenAI({ modelName }).bindTools(toolkit)
  const response = await openAI.invoke([new HumanMessage(question), ...messages])
  return { messages: [response] }
}

const shouldUseSearchTools = ({ messages }: ChatState) => {
  const message = messages[messages.length - 1] as AIMessage
  return message?.tool_calls?.length > 0 ? 'searchTools' : 'adjustment'
}

const chatNode = async ({ conversation }: ChatState, { configurable }: RunnableConfig) => {
  const chatMode = (configurable?.chatMode ?? 'normal') as string
  const modelName = (configurable?.modelName ?? 'gpt-4o-mini') as string
  const question = (configurable?.question ?? '') as string

  const openAI = new ChatOpenAI({ modelName, temperature: 1 })
  const prompt = new PromptTemplate({
    template: chatMode === 'positive' ? CHAT_POSITIVE_PROMPT : CHAT_PROMPT,
    inputVariables: ['context', 'question']
  })

  const response = await prompt.pipe(openAI).invoke({
    question: question,
    context: conversation
      .filter((message) => message.additional_kwargs?.chatMode === chatMode || message.getType() === 'human')
      .map((message) => message.content)
      .join('\n')
  })

  return { messages: [response] }
}

const adjustmentNode = async ({ messages }: ChatState, { configurable }: RunnableConfig) => {
  const chatMode = (configurable?.chatMode ?? 'normal') as string
  const modelName = (configurable?.modelName ?? 'gpt-4o-mini') as string
  const message = messages[messages.length - 1]

  const openAI = new ChatOpenAI({ modelName })
  const prompt = new PromptTemplate({ template: ADJUSTMENT_PROMPT, inputVariables: ['content'] })

  const response = await prompt.pipe(openAI).invoke({ content: message.content })
  response.additional_kwargs = { ...response.additional_kwargs, chatMode }

  return { conversation: [response] }
}

const cleanupNode = ({ conversation, messages }: ChatState) => {
  return {
    messages: messages.map(({ id }) => new RemoveMessage({ id })),
    conversation: conversation.slice(0, -25).map(({ id }) => new RemoveMessage({ id }))
  }
}

/**
 * Get a compiled chat graph.
 */
export const chatGraph = () => {
  const annotation = Annotation.Root({
    messages: Annotation<AIMessage[]>({ reducer: messagesStateReducer }),
    conversation: Annotation<HumanMessage[]>({ reducer: messagesStateReducer })
  })
  const checkpointer = createDynamoDBSaver()

  const summarizationNode = summarizationGraph().compile({ checkpointer })

  const graph = new StateGraph(annotation)
    .addNode('summarization', summarizationNode)
    .addNode('search', searchNode)
    .addNode('chat', chatNode)
    .addNode('adjustment', adjustmentNode)
    .addNode('cleanup', cleanupNode)
    .addNode('searchTools', new ToolNode(toolkit))
    .addConditionalEdges('__start__', shouldInvoke, ['summarization', 'search', 'chat'])
    .addEdge('summarization', 'adjustment')
    .addConditionalEdges('search', shouldUseSearchTools, ['searchTools', 'adjustment'])
    .addEdge('searchTools', 'search')
    .addEdge('chat', 'adjustment')
    .addEdge('adjustment', 'cleanup')
    .addEdge('cleanup', '__end__')

  return graph.compile({ checkpointer })
}
