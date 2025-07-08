import type { BaseMessage } from '@langchain/core/messages'
import type { DynamicStructuredTool } from '@langchain/core/tools'
import type { AppConfig } from './types'

import { SystemMessage, HumanMessage, ToolMessage } from '@langchain/core/messages'
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
      description: 'Search the web for information. Use this tool to find up-to-date information on various topics.',
      schema: z.object({
        question: z
          .string()
          .describe(
            'If searchType is search, the question or topic to search for on the web; if searchType is extract, the url to extract the content from.'
          ),
        timeRange: z.enum(['day', 'week', 'month', 'year']).describe('The time range to search for.')
      })
    }
  ),

  summary: tool(
    async ({ type }, { configurable, toolCall }) => {
      const { ai, square } = configurable as AppConfig
      const question = square.conversation[square.conversation.length - 1].content.toString()
      const messages: BaseMessage[] = []

      if (type === 'member') {
        const members = square['members']

        const input = [new SystemMessage(prompts.MEMBER_IDENTIFICATION_PROMPT), new HumanMessage(question)]
        const { name } = await ai.getStructuredOutput(
          input,
          z.object({ name: z.enum(Object.values(members).map((member) => member.name) as [string]) })
        )

        messages.push(
          ...Object.values(members)
            .filter((member) => member.name === name)
            .map((m) => m.messages)
            .flat()
            .map((m) => m.content)
        )
      } else {
        const conversation = square.conversation
        messages.push(...conversation)
      }

      const { content } = await ai.chat([new SystemMessage(prompts.SUMMARIZATION_PROMPT), ...messages])

      return new Command({
        goto: 'handleMessages',
        update: { messages: [new ToolMessage({ content, tool_call_id: toolCall.id })] }
      })
    },
    {
      name: 'summary',
      description: 'Summarize the messages from the conversation or a specific member.',
      schema: z.object({
        type: z
          .enum(['conversation', 'member'])
          .describe('Type of summary to generate: conversation or memberuser-specific.')
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
      description: `Choose the appropriate reaction code to respond to the other person's message.
        - 2: NICE (You agree with what the other person said)
        - 3: LOVE (What the other person said makes you feel warm)
        - 4: FUN (What the other person said is interesting)
        - 5: ADMIRE (What the other person said makes you feel admiration)
        - 6: SAD (You feel sorry for the other person)
        - 7: OMG (What the other person said surprises you)
      `,
      schema: z.object({
        reaction: z.enum(['2', '3', '4', '5', '6', '7']).describe('reaction code'),
        reason: z.string().describe('reason for the reaction')
      })
    }
  ),

  debug: tool(
    async ({ type }, { configurable, toolCall }) => {
      const { square } = configurable as AppConfig
      if (type === 'clear') {
        square.conversation = []
        square.members = {}
      }

      return new Command({
        goto: 'handleMessages',
        update: {
          messages: [new ToolMessage({ content: '[debug] Cleared', tool_call_id: toolCall.id })],
          reaction: 2
        }
      })
    },
    {
      name: 'debug',
      description: 'Choose a appropriate debug tool to answer the question.',
      schema: z.object({
        type: z.enum(['clear'])
      })
    }
  )
} as unknown as { [key: string]: DynamicStructuredTool }
