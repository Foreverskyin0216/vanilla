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
      country: 'taiwan',
      includeAnswer: true,
      maxResults: 1,
      searchDepth: 'advanced'
    })
    return answer
  }

  public async extract(url: string) {
    const { results } = await this.client.extract([url])

    const result = results.find((result) => result.url === url)
    if (!result) {
      return ''
    }

    return result.rawContent
  }
}
