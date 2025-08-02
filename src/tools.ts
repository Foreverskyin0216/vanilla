import type { DynamicStructuredTool } from '@langchain/core/tools'
import type { AppConfig } from './types'

import { Document } from '@langchain/core/documents'
import { HumanMessage, SystemMessage, ToolMessage } from '@langchain/core/messages'
import { tool } from '@langchain/core/tools'
import { Command } from '@langchain/langgraph'
import { z } from 'zod'

import * as prompts from './prompts'

export const tools = {
  websearch: tool(
    async ({ question, timeRange }, { configurable, toolCall }) => {
      const tavily = configurable['search'] as AppConfig['search']

      const answer = await tavily.search(question, timeRange)
      return new Command({
        goto: 'handleMessages',
        update: { messages: [new ToolMessage({ content: answer, tool_call_id: toolCall.id })] }
      })
    },
    {
      name: 'websearch',
      description: `When the user's question requires
        - real-time information
        - specific time range
        - specific domain information
        - specific topic information
        - specific event information
        - specific location information
      use this tool.
      `,
      schema: z.object({
        question: z.string().describe('The question or topic to search for on the web.'),
        timeRange: z.enum(['day', 'week', 'month', 'year']).describe('The time range to search for.')
      })
    }
  ),

  summary: tool(
    async (_, { configurable, toolCall }) => {
      const { ai, square } = configurable as AppConfig
      const { content } = await ai.chat([new SystemMessage(prompts.SUMMARIZATION_PROMPT), ...square.conversation])
      return new Command({
        goto: 'handleMessages',
        update: { messages: [new ToolMessage({ content, tool_call_id: toolCall.id })] }
      })
    },
    {
      name: 'summary',
      description: `When the user's question requires
        - summary of the conversation
      use this tool.
      `,
      schema: z.object({})
    }
  ),

  chatHistory: tool(
    async ({ question }, { configurable, toolCall }) => {
      const { ai, square } = configurable as AppConfig

      const retriever = square.vectorStore.asRetriever()
      const documents = await retriever.invoke(question)
      const context = documents.map((doc) => new HumanMessage(doc.pageContent))

      const { content } = await ai.chat([
        new SystemMessage(prompts.DO_RETRIEVAL),
        ...context,
        new HumanMessage(question)
      ])

      return new Command({
        goto: 'handleMessages',
        update: { messages: [new ToolMessage({ content, tool_call_id: toolCall.id })] }
      })
    },
    {
      name: 'chatHistory',
      description: `When the user's question is related to someone in the chat room,
      but the answer is not in the conversation,
      use this tool to retrieve the information from the long-term chat history.
      `,
      schema: z.object({
        question: z.string().describe('The question or topic to search for in the chat history.')
      })
    }
  ),

  updateChatHistory: tool(
    async ({ content, target }, { configurable, toolCall }) => {
      const { square } = configurable as AppConfig
      await square.vectorStore.addDocuments([new Document({ id: target, pageContent: content })])
      return new Command({
        goto: 'handleMessages',
        update: {
          reaction: 2,
          messages: [new ToolMessage({ content: 'Done', tool_call_id: toolCall.id })]
        }
      })
    },
    {
      name: 'updateChatHistory',
      description: 'When the user wants you to remember something, use this tool.',
      schema: z.object({
        content: z.string().describe('The content to remember. It should be a short summary or some key points.'),
        target: z.string().describe(
          `The target user to remember the content for.
          If not specified, the content will be remembered for the user who is currently talking.`
        )
      })
    }
  ),

  react: tool(
    async ({ reaction, reason }, { toolCall }) => {
      return new Command({
        goto: 'handleMessages',
        update: {
          reaction: Number(reaction),
          messages: [new ToolMessage({ content: reason, tool_call_id: toolCall.id })]
        }
      })
    },
    {
      name: 'react',
      description: `When your feelings meet the following conditions, use this tool to react to the other person's message.
      Choose the appropriate reaction code to respond to the other person's message.
        - 2: NICE (You agree with what the other person said)
        - 3: LOVE (What the other person said makes you feel warm)
        - 4: FUN (What the other person said is interesting)
        - 5: ADMIRE (What the other person said makes you feel admiration)
        - 6: SAD (You feel sorry for the other person)
        - 7: OMG (What the other person said surprises you)
      
      DO NOT use this tool every time.
      `,
      schema: z.object({
        reaction: z.enum(['2', '3', '4', '5', '6', '7']).describe('reaction code'),
        reason: z.string().describe('reason for the reaction')
      })
    }
  )
} as unknown as { [key: string]: DynamicStructuredTool }
