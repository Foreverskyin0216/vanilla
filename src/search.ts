import type { TavilyClient, TavilyClientOptions } from '@tavily/core'

import { tavily } from '@tavily/core'

export class Search {
  private client: TavilyClient

  constructor(config: TavilyClientOptions = {}) {
    if (!config.apiKey && !process.env.TAVILY_API_KEY) {
      throw new Error('Search setup failed. A Tavily API key is required.')
    }
    this.client = tavily(config)
  }

  public async search(question: string) {
    const { answer } = await this.client.search(question, {
      autoParameters: true,
      includeAnswer: true,
      searchDepth: 'advanced'
    })
    return answer
  }
}
