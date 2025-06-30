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
    async ({ question }, { configurable, toolCall }) => {
      const tavily = configurable['search'] as AppConfig['search']
      const answer = await tavily.search(question)
      return new Command({
        goto: 'handleMessages',
        update: { messages: [new ToolMessage({ content: answer, tool_call_id: toolCall.id })] }
      })
    },
    {
      name: 'websearch',
      description: 'Search the web for information. Use this tool to find up-to-date information on various topics.',
      schema: z.object({ question: z.string().describe('The question or topic to search for on the web.') })
    }
  ),

  reply: tool(
    async ({ type }, { configurable, toolCall }) => {
      const { ai, square } = configurable as AppConfig
      const question = square.conversation[square.conversation.length - 1].content.toString()
      const messages: BaseMessage[] = []

      if (type === 'member') {
        const members = square['members']

        const input = [new SystemMessage(prompts.MEMBER_IDENTIFICATION_PROMPT), new HumanMessage(question)]
        const { name } = await ai.getStructuredOutput(
          input,
          z.object({ name: z.enum(Object.values(members).map((member) => member.name) as [string]) }),
          'o3-mini'
        )

        messages.push(
          ...Object.values(members)
            .filter((member) => member.name === name)
            .map((m) => m.messages)
            .flat()
            .map((m) => m.content)
        )
        messages.push(new HumanMessage(question))
      } else {
        const conversation = square.conversation
        messages.push(...conversation)
      }

      const input = [new SystemMessage(prompts.SUMMARIZATION_PROMPT), ...messages]
      const response = await ai.chat(input)

      return new Command({
        goto: 'handleMessages',
        update: { messages: [new ToolMessage({ content: response.content, tool_call_id: toolCall.id })] }
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
  )
} as unknown as { [key: string]: DynamicStructuredTool }
