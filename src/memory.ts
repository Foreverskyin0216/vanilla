import type { EmbeddingsInterface } from '@langchain/core/embeddings'
import type { AI } from './ai'
import type {
  LongTermMemory,
  PersonalMemory,
  RelationshipMemory,
  EventMemory,
  MemorySearchResult,
  MemoryEvaluation
} from './types'

import { promises as fs } from 'fs'
import { SystemMessage, HumanMessage } from '@langchain/core/messages'

import * as prompts from './prompts'

export class LongTermMemoryManager {
  private ai: AI
  private botName: string
  private memoryPath: string
  private embeddings: EmbeddingsInterface
  private memory: LongTermMemory = {
    personal: {},
    relationships: {},
    events: [],
    preferences: {}
  }
  private memoryLoaded = false

  constructor(ai: AI, botName: string, memoryPath = './data/memory.json') {
    this.ai = ai
    this.botName = botName
    this.embeddings = ai.createEmbeddings()
    this.memoryPath = memoryPath
  }

  async initialize() {
    try {
      // Ensure data directory exists
      const dir = this.memoryPath.split('/').slice(0, -1).join('/')
      await fs.mkdir(dir, { recursive: true })

      // Check if file exists but don't load it yet (lazy loading)
      await fs.access(this.memoryPath)
      console.log('Memory file found, will load on demand')
    } catch {
      // If file doesn't exist, start with empty memory
      await this.saveMemory()
      this.memoryLoaded = true
    }
  }

  private async loadMemoryIfNeeded() {
    if (this.memoryLoaded) return

    try {
      const data = await fs.readFile(this.memoryPath, 'utf8')
      this.memory = JSON.parse(data)
      this.memoryLoaded = true

      // Run cleanup on first load
      await this.cleanupOldMemories()
    } catch (error) {
      console.error('Failed to load memory:', error)
      this.memoryLoaded = true
    }
  }

  private async saveMemory() {
    // Save with minimal JSON formatting to reduce file size
    const jsonString = JSON.stringify(this.memory)
    await fs.writeFile(this.memoryPath, jsonString)
  }

  async storePersonalMemory(userName: string, fact: string, category: string = 'general') {
    await this.loadMemoryIfNeeded()

    if (!this.memory.personal[userName]) {
      this.memory.personal[userName] = {
        facts: [],
        traits: [],
        preferences: [],
        history: []
      }
    }

    // Check for similar existing memories to avoid duplicates
    const userMemory = this.memory.personal[userName]
    const categoryArray = (userMemory[category as keyof typeof userMemory] as PersonalMemory[]) || []

    // Simple duplicate check - if very similar content exists, don't store
    const isDuplicate = categoryArray.some(
      (existing) => this.calculateSimilarity(existing.content.toLowerCase(), fact.toLowerCase()) > 0.8
    )

    if (isDuplicate) {
      return 'duplicate'
    }

    const embedding = await this.embeddings.embedQuery(fact)
    const personalMemory: PersonalMemory = {
      id: Date.now().toString(),
      content: fact,
      category,
      timestamp: new Date().toISOString(),
      embedding: this.compressEmbedding(embedding)
    }

    categoryArray.push(personalMemory)

    // Limit personal memories per category to prevent excessive growth
    const MAX_MEMORIES_PER_CATEGORY = 10
    if (categoryArray.length > MAX_MEMORIES_PER_CATEGORY) {
      // Keep most recent ones
      categoryArray.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
      categoryArray.splice(MAX_MEMORIES_PER_CATEGORY)
    }

    userMemory[category as keyof typeof userMemory] = categoryArray as PersonalMemory[]

    await this.saveMemory()
    return personalMemory.id
  }

  async storeRelationshipMemory(
    userName: string,
    botName: string,
    interaction: string,
    sentiment: 'positive' | 'negative' | 'neutral' = 'neutral'
  ) {
    await this.loadMemoryIfNeeded()

    const relationshipKey = `${userName}-${botName}`
    if (!this.memory.relationships[relationshipKey]) {
      this.memory.relationships[relationshipKey] = {
        userName,
        botName,
        interactions: [],
        dynamics: [],
        milestones: []
      }
    }

    const embedding = await this.embeddings.embedQuery(interaction)
    const relationshipMemory: RelationshipMemory = {
      id: Date.now().toString(),
      content: interaction,
      sentiment,
      timestamp: new Date().toISOString(),
      embedding: this.compressEmbedding(embedding)
    }

    this.memory.relationships[relationshipKey].interactions.push(relationshipMemory)

    // Reduced limit: Keep only last 20 interactions per relationship
    if (this.memory.relationships[relationshipKey].interactions.length > 20) {
      this.memory.relationships[relationshipKey].interactions.shift()
    }

    await this.saveMemory()
    return relationshipMemory.id
  }

  async storeEventMemory(content: string, participants: string[], importance: number = 1) {
    await this.loadMemoryIfNeeded()

    // Check for duplicate events
    const isDuplicate = this.memory.events.some(
      (existing) => this.calculateSimilarity(existing.content.toLowerCase(), content.toLowerCase()) > 0.8
    )

    if (isDuplicate) {
      return 'duplicate'
    }

    const embedding = await this.embeddings.embedQuery(content)
    const eventMemory: EventMemory = {
      id: Date.now().toString(),
      content,
      participants,
      importance,
      timestamp: new Date().toISOString(),
      embedding: this.compressEmbedding(embedding)
    }

    this.memory.events.push(eventMemory)

    // Reduced limit: Keep only last 30 events, prioritizing by importance
    if (this.memory.events.length > 30) {
      this.memory.events.sort((a, b) => b.importance - a.importance)
      this.memory.events = this.memory.events.slice(0, 30)
    }

    await this.saveMemory()
    return eventMemory.id
  }

  async searchMemories(query: string, userName?: string, limit = 5): Promise<MemorySearchResult[]> {
    await this.loadMemoryIfNeeded()

    const queryEmbedding = await this.embeddings.embedQuery(query)
    const results: MemorySearchResult[] = []

    // Search personal memories
    if (userName && this.memory.personal[userName]) {
      const personal = this.memory.personal[userName]
      for (const category of ['facts', 'traits', 'preferences', 'history']) {
        for (const memory of personal[category] || []) {
          const similarity = this.cosineSimilarity(queryEmbedding, this.decompressEmbedding(memory.embedding))
          results.push({
            type: 'personal',
            category,
            content: memory.content,
            similarity,
            timestamp: memory.timestamp,
            id: memory.id
          })
        }
      }
    }

    // Search relationship memories
    for (const [relationshipKey, relationship] of Object.entries(this.memory.relationships)) {
      if (!userName || relationshipKey.includes(userName)) {
        for (const memory of relationship.interactions) {
          const similarity = this.cosineSimilarity(queryEmbedding, this.decompressEmbedding(memory.embedding))
          results.push({
            type: 'relationship',
            category: 'interaction',
            content: memory.content,
            similarity,
            timestamp: memory.timestamp,
            id: memory.id,
            sentiment: memory.sentiment
          })
        }
      }
    }

    // Search event memories
    for (const memory of this.memory.events) {
      if (!userName || memory.participants.includes(userName)) {
        const similarity = this.cosineSimilarity(queryEmbedding, this.decompressEmbedding(memory.embedding))
        results.push({
          type: 'event',
          category: 'general',
          content: memory.content,
          similarity,
          timestamp: memory.timestamp,
          id: memory.id,
          importance: memory.importance
        })
      }
    }

    // Sort by similarity and return top results
    return results.sort((a, b) => b.similarity - a.similarity).slice(0, limit)
  }

  async getPersonalContext(userName: string): Promise<string> {
    await this.loadMemoryIfNeeded()

    if (!this.memory.personal[userName]) {
      return '目前沒有關於這個人的記憶。'
    }

    const personal = this.memory.personal[userName]
    const context = []

    if (personal.facts && personal.facts.length > 0) {
      context.push(`已知事實: ${personal.facts.map((f) => f.content).join(', ')}`)
    }

    if (personal.traits && personal.traits.length > 0) {
      context.push(`個人特質: ${personal.traits.map((t) => t.content).join(', ')}`)
    }

    if (personal.preferences && personal.preferences.length > 0) {
      context.push(`偏好設定: ${personal.preferences.map((p) => p.content).join(', ')}`)
    }

    return context.length > 0 ? context.join('\n') : '目前沒有詳細的個人資訊。'
  }

  async getRelationshipContext(userName: string, botName: string): Promise<string> {
    await this.loadMemoryIfNeeded()

    const relationshipKey = `${userName}-${botName}`
    const relationship = this.memory.relationships[relationshipKey]

    if (!relationship || relationship.interactions.length === 0) {
      return '這是你們第一次見面。'
    }

    const recentInteractions = relationship.interactions.slice(-5)
    const positiveCount = relationship.interactions.filter((i) => i.sentiment === 'positive').length
    const negativeCount = relationship.interactions.filter((i) => i.sentiment === 'negative').length

    let relationshipStatus = '普通'
    if (positiveCount > negativeCount * 2) {
      relationshipStatus = '良好'
    } else if (negativeCount > positiveCount * 2) {
      relationshipStatus = '緊張'
    }

    return `關係狀態: ${relationshipStatus}\n最近的互動: ${recentInteractions.map((i) => i.content).join(', ')}`
  }

  private cosineSimilarity(a: number[], b: number[]): number {
    let dotProduct = 0
    let normA = 0
    let normB = 0

    for (let i = 0; i < a.length; i++) {
      dotProduct += a[i] * b[i]
      normA += a[i] * a[i]
      normB += b[i] * b[i]
    }

    return dotProduct / (Math.sqrt(normA) * Math.sqrt(normB))
  }

  // Simple text similarity for duplicate detection (avoids embedding computation)
  private calculateSimilarity(text1: string, text2: string): number {
    const words1 = text1.split(/\s+/)
    const words2 = text2.split(/\s+/)

    if (text1 === text2) return 1.0

    // Jaccard similarity
    const set1 = new Set(words1)
    const set2 = new Set(words2)
    const intersection = new Set([...set1].filter((x) => set2.has(x)))
    const union = new Set([...set1, ...set2])

    return intersection.size / union.size
  }

  // Compress embeddings to reduce file size (keep only most important dimensions)
  private compressEmbedding(embedding: number[]): number[] {
    // Keep only every 8th dimension to reduce size by ~87.5%
    const compressed = []
    for (let i = 0; i < embedding.length; i += 8) {
      compressed.push(embedding[i])
    }
    return compressed
  }

  // Decompress embeddings for similarity calculations
  private decompressEmbedding(compressed: number[]): number[] {
    // Reconstruct by interpolating missing values (8x expansion)
    const decompressed = []
    for (let i = 0; i < compressed.length; i++) {
      decompressed.push(compressed[i])
      // Fill gaps with interpolated values
      if (i < compressed.length - 1) {
        const diff = (compressed[i + 1] - compressed[i]) / 8
        for (let j = 1; j < 8; j++) {
          decompressed.push(compressed[i] + diff * j)
        }
      } else {
        // For last element, repeat the value
        for (let j = 1; j < 8; j++) {
          decompressed.push(compressed[i])
        }
      }
    }
    return decompressed
  }

  // Cleanup old memories to prevent file size growth
  private async cleanupOldMemories() {
    const oneMonthAgo = new Date()
    oneMonthAgo.setMonth(oneMonthAgo.getMonth() - 1)

    // Clean up old events (keep only last month or high importance)
    this.memory.events = this.memory.events.filter(
      (event) => new Date(event.timestamp) > oneMonthAgo || event.importance >= 4
    )

    // Clean up old relationship interactions (keep only last month)
    for (const relationshipKey in this.memory.relationships) {
      const relationship = this.memory.relationships[relationshipKey]
      relationship.interactions = relationship.interactions.filter(
        (interaction) => new Date(interaction.timestamp) > oneMonthAgo
      )
    }

    // Clean up old personal memories (keep only important or recent ones)
    for (const userId in this.memory.personal) {
      const personal = this.memory.personal[userId]
      for (const category of ['facts', 'traits', 'preferences', 'history']) {
        const categoryArray = personal[category] || []
        if (categoryArray.length > 5) {
          // Keep only most recent 5 or those with long content (more detailed)
          const filtered = categoryArray
            .filter((memory) => new Date(memory.timestamp) > oneMonthAgo || memory.content.length > 30)
            .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
            .slice(0, 8)

          personal[category] = filtered
        }
      }
    }

    console.log('Memory cleanup completed')
  }

  async evaluateConversation(userName: string, userMessage: string, botResponse: string): Promise<MemoryEvaluation> {
    await this.loadMemoryIfNeeded()

    const evaluationPrompt = prompts.MEMORY_EVALUATION_PROMPT.replace('{userMessage}', userMessage).replace(
      '{botResponse}',
      botResponse
    )

    try {
      // Use regular chat instead of structured output to avoid schema compatibility issues
      const evaluationResponse = await this.ai.chat([
        new SystemMessage(`${evaluationPrompt}\n\n${prompts.MEMORY_EVALUATION_JSON_FORMAT}`),
        new HumanMessage(`${userName}: ${userMessage}\n${this.botName}: ${botResponse}`)
      ])

      const jsonMatch = evaluationResponse.content.toString().match(/\{[\s\S]*\}/)
      if (jsonMatch) {
        const evaluation = JSON.parse(jsonMatch[0]) as MemoryEvaluation
        return evaluation
      }

      return {
        shouldStore: false,
        personalInfo: [],
        sentiment: 'neutral',
        interactionSummary: '解析失敗'
      }
    } catch (error) {
      console.error('Memory evaluation error:', error)
      return {
        shouldStore: false,
        personalInfo: [],
        sentiment: 'neutral',
        interactionSummary: '評估失敗'
      }
    }
  }

  async getRelevantContext(userId: string, currentMessage: string): Promise<string> {
    await this.loadMemoryIfNeeded()

    if (!this.memory.personal[userId] && !this.memory.relationships[`${userId}-香草`]) {
      return ''
    }

    try {
      // Search for relevant memories using semantic similarity
      const relevantMemories = await this.searchMemories(currentMessage, userId, 3)

      if (relevantMemories.length === 0) {
        return ''
      }

      // Generate compact context using AI
      const contextPrompt = prompts.CONTEXT_GENERATION_PROMPT.replace(
        '{relevantMemories}',
        relevantMemories.map((m) => `- ${m.content}`).join('\n')
      ).replace('{currentMessage}', currentMessage)

      const contextResponse = await this.ai.chat([new SystemMessage(contextPrompt), new HumanMessage('生成背景資訊')])

      return contextResponse.content.toString()
    } catch (error) {
      console.error('Context generation error:', error)
      return ''
    }
  }

  async autoProcessConversation(userName: string, userMessage: string, botResponse: string, botName: string) {
    try {
      const evaluation = await this.evaluateConversation(userName, userMessage, botResponse)

      if (!evaluation.shouldStore) {
        return
      }

      // Store personal information extracted by AI
      for (const info of evaluation.personalInfo) {
        await this.storePersonalMemory(info.content, info.category)
      }

      // Store relationship interaction
      if (evaluation.interactionSummary && evaluation.interactionSummary !== '評估失敗') {
        await this.storeRelationshipMemory(botName, evaluation.interactionSummary, evaluation.sentiment)
      }
    } catch (error) {
      console.error('Auto memory processing error:', error)
    }
  }
}
