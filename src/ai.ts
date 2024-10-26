import type { BaseMessage } from '@langchain/core/messages'
import type { DynamicStructuredTool } from '@langchain/core/tools'
import type { ChatOpenAICallOptions, OpenAIChatInput } from '@langchain/openai'
import type { ZodJSONSchema } from 'zod'

import { ChatOpenAI, OpenAIEmbeddings } from '@langchain/openai'
import { Embeddings } from '@langchain/core/embeddings'

export class AI {
  private _llms: Record<string, ChatOpenAI> = {}
  private _embeddings: Record<string, Embeddings> = {}

  constructor(config: Partial<ChatOpenAICallOptions & OpenAIChatInput> = {}) {
    if (!config.apiKey && !config.openAIApiKey && !process.env.OPENAI_API_KEY) {
      throw new Error('LLM setup failed. An OpenAI API key is required.')
    }
    this._llms['default'] = new ChatOpenAI({ ...config, configuration: config, model: config.model ?? 'gpt-4.1' })
    this._embeddings['default'] = new OpenAIEmbeddings({
      ...config,
      configuration: config,
      model: 'text-embedding-3-small'
    })
  }

  private _clone<T>(instance: T): T {
    const newObject = Object.create(Object.getPrototypeOf(instance))
    return Object.assign(newObject, JSON.parse(JSON.stringify(instance)))
  }

  public async callTools(tools: DynamicStructuredTool[], messages: BaseMessage[], model = 'default') {
    if (!this._llms[model]) {
      const clonedLLM = this._clone<ChatOpenAI>(this._llms.default)
      this._llms[model] = clonedLLM
    }

    const runnable = this._llms[model].bindTools(tools, { strict: true })
    const response = await runnable.invoke(messages)

    return response
  }

  public async chat(messages: BaseMessage[], model = 'default') {
    if (!this._llms[model]) {
      const clonedLLM = this._clone<ChatOpenAI>(this._llms.default)
      this._llms[model] = clonedLLM
    }
    return this._llms[model].invoke(messages)
  }

  public async getStructuredOutput<T>(messages: BaseMessage[], schema: ZodJSONSchema, model = 'default') {
    if (!this._llms[model]) {
      const clonedLLM = this._clone<ChatOpenAI>(this._llms.default)
      this._llms[model] = clonedLLM
    }

    const runnable = this._llms[model].withStructuredOutput(schema, { strict: true })
    const response = await runnable.invoke(messages)

    return response as T
  }

  public createEmbeddings(model = 'default') {
    if (!this._embeddings[model]) {
      const clonedEmbeddings = this._clone<Embeddings>(this._embeddings.default)
      this._embeddings[model] = clonedEmbeddings
    }

    return this._embeddings[model]
  }
}
