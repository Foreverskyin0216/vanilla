import type { BaseMessage } from '@langchain/core/messages'
import type { RunnableConfig } from '@langchain/core/runnables'
import type { AppConfig } from './types'

import { SystemMessage } from '@langchain/core/messages'
import { Annotation, Command, StateGraph, messagesStateReducer } from '@langchain/langgraph'
import { ToolNode } from '@langchain/langgraph/prebuilt'

import * as prompts from './prompts'
import { tools } from './tools'

const annotation = Annotation.Root({
  messages: Annotation<BaseMessage[]>({ reducer: messagesStateReducer }),
  responseType: Annotation<string>,
  reaction: Annotation<0 | 1 | 2 | 3 | 4 | 5 | 6 | 7>
})

type State = typeof annotation.State

const handleMessages = async (state: State, { configurable }: RunnableConfig) => {
  const { ai } = configurable as AppConfig

  const input = [new SystemMessage(prompts.VANILLA_PERSONALITY), ...state.messages]
  const response = await ai.callTools(Object.values(tools), input)

  return new Command({ goto: response.tool_calls?.length ? 'callTools' : '__end__', update: { messages: [response] } })
}

export const buildGraph = () => {
  const graph = new StateGraph(annotation)
    .addNode('handleMessages', handleMessages, { ends: ['callTools'] })
    .addNode('callTools', new ToolNode(Object.values(tools)), { ends: ['handleMessages'] })
    .addEdge('__start__', 'handleMessages')

  return graph.compile()
}
