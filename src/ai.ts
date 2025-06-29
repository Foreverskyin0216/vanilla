import type { BaseMessage } from '@langchain/core/messages'
import type { DynamicStructuredTool } from '@langchain/core/tools'
import type { ChatOpenAICallOptions, OpenAIChatInput } from '@langchain/openai'
import type { ZodSchema } from 'zod'

import { ChatOpenAI } from '@langchain/openai'

export class AI {
  private _llms: Record<string, ChatOpenAI> = {}

  constructor(config: Partial<ChatOpenAICallOptions & OpenAIChatInput> = {}) {
    if (!config.apiKey && !config.openAIApiKey && !process.env.OPENAI_API_KEY) {
      throw new Error('LLM setup failed. An OpenAI API key is required.')
    }
    this._llms['default'] = new ChatOpenAI({ ...config, configuration: config, model: config.model ?? 'gpt-4.1' })
  }

  private _cloneLLM(llm: ChatOpenAI): ChatOpenAI {
    const instance = Object.create(Object.getPrototypeOf(llm))
    return Object.assign(instance, JSON.parse(JSON.stringify(llm)))
  }

  public async callTools(tools: DynamicStructuredTool[], messages: BaseMessage[], model = 'default') {
    if (!this._llms[model]) {
      const clonedLLM = this._cloneLLM(this._llms.default)
      this._llms[model] = clonedLLM
    }

    const runnable = this._llms[model].bindTools(tools, { strict: true })
    const response = await runnable.invoke(messages)

    return response
  }

  public async chat(messages: BaseMessage[], model = 'default') {
    if (!this._llms[model]) {
      const clonedLLM = this._cloneLLM(this._llms.default)
      this._llms[model] = clonedLLM
    }
    return this._llms[model].invoke(messages)
  }

  public async getStructuredOutput<T>(messages: BaseMessage[], schema: ZodSchema<T>, model = 'default') {
    if (!this._llms[model]) {
      const clonedLLM = this._cloneLLM(this._llms.default)
      this._llms[model] = clonedLLM
    }

    const runnable = this._llms[model].withStructuredOutput(schema, { strict: true })
    const response = await runnable.invoke(messages)

    return response as T
  }
}
