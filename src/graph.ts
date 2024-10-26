import type { RunnableConfig } from '@langchain/core/runnables'
import type { AppConfig, GraphState } from './types'

import { BaseMessage, SystemMessage, HumanMessage } from '@langchain/core/messages'
import { PromptTemplate } from '@langchain/core/prompts'
import { Annotation, Command, StateGraph, messagesStateReducer } from '@langchain/langgraph'
import { ToolNode } from '@langchain/langgraph/prebuilt'

import * as prompts from './prompts'
import { tools } from './tools'

const annotation = Annotation.Root({
  messages: Annotation<BaseMessage[]>({ reducer: messagesStateReducer }),
  reaction: Annotation<(0 | 1 | 2 | 3 | 4 | 5 | 6 | 7)[]>({
    default: () => [],
    reducer: (prev, next) => prev.concat(next)
  }),
  memoryContext: Annotation<string>(),
  userName: Annotation<string>(),
  userMessage: Annotation<string>(),
  toolCallCount: Annotation<number>()
})

type State = GraphState

// Memory loading node - loads relevant context before processing
const loadMemoryContext = async (state: State, { configurable }: RunnableConfig) => {
  const { square } = configurable as AppConfig

  try {
    const context = await square.store.getRelevantContext(state.userName, state.userMessage)
    return new Command({
      goto: 'processMessage',
      update: { memoryContext: context }
    })
  } catch (error) {
    console.error('Memory loading failed:', error)
    return new Command({
      goto: 'processMessage',
      update: { memoryContext: '' }
    })
  }
}

// Main message processing with enhanced context
const processMessage = async (state: State, { configurable }: RunnableConfig) => {
  const { ai, botName } = configurable as AppConfig
  const prompt = await PromptTemplate.fromTemplate(prompts.VANILLA_PERSONALITY).format({ botName })

  // Enhance messages with memory context if available
  let enhancedMessages = [...state.messages]
  if (state.memoryContext) {
    const contextMessage = new HumanMessage(`[記憶背景: ${state.memoryContext}]`)
    enhancedMessages = [...state.messages.slice(0, -1), contextMessage, state.messages[state.messages.length - 1]]
  }

  const input = [new SystemMessage(prompt), ...enhancedMessages]

  try {
    const response = await ai.callTools(Object.values(tools), input)

    // Prevent infinite tool loops
    const hasToolCalls = response.tool_calls && response.tool_calls.length > 0
    const toolCallLimit = (state.toolCallCount || 0) >= 3

    if (hasToolCalls && !toolCallLimit) {
      return new Command({
        goto: 'executeTools',
        update: {
          messages: [response],
          toolCallCount: (state.toolCallCount || 0) + 1
        }
      })
    } else {
      return new Command({
        goto: 'postProcess',
        update: { messages: [response] }
      })
    }
  } catch (error) {
    console.error('Message processing failed:', error)
    // Fallback response
    const fallbackResponse = new HumanMessage('嗯...我有點累了 (´･ω･`)')
    return new Command({
      goto: '__end__',
      update: { messages: [fallbackResponse], reaction: 6 }
    })
  }
}

// Post-processing for memory storage and cleanup
const postProcess = async (state: State, { configurable }: RunnableConfig) => {
  const { botName, square } = configurable as AppConfig

  try {
    // Auto-store conversation in memory (async, don't wait)
    if (state.userMessage && state.messages.length > 0) {
      const lastResponse = state.messages[state.messages.length - 1]
      square.store
        .autoProcessConversation(state.userName, state.userMessage, lastResponse.content.toString(), botName)
        .catch((error) => console.error('Memory storage failed:', error))
    }
  } catch (error) {
    console.error('Post-processing failed:', error)
  }

  return new Command({ goto: '__end__' })
}

export const buildGraph = () => {
  const graph = new StateGraph(annotation)
    .addNode('loadMemoryContext', loadMemoryContext, { ends: ['processMessage'] })
    .addNode('processMessage', processMessage, { ends: ['executeTools', 'postProcess', '__end__'] })
    .addNode('executeTools', new ToolNode(Object.values(tools)), { ends: ['processMessage'] })
    .addNode('postProcess', postProcess, { ends: ['__end__'] })
    .addEdge('__start__', 'loadMemoryContext')

  return graph.compile()
}
