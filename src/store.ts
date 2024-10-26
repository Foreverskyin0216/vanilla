import type { EmbeddingsInterface } from '@langchain/core/embeddings'
import type { MemoryVector } from './types'

import { Document } from '@langchain/core/documents'
import { VectorStore } from '@langchain/core/vectorstores'

/** In-memory, ephemeral vector store. */
export class MemoryVectorStore extends VectorStore {
  /** The type of filter function for the vector store. */
  declare FilterType: (doc: Document) => boolean

  /** Array of vectors stored in memory. */
  vectors: MemoryVector[] = []

  constructor(embeddings: EmbeddingsInterface) {
    super(embeddings, {})
  }

  /** Defines the type of vector store. */
  _vectorstoreType() {
    return 'memory'
  }

  /**
   * The method to query vectors in the memory vector store.
   * It calculates the cosine similarity between the query vector and each vector in the store,
   * sorts the results by similarity, and returns the top `k` results.
   *
   * @param query The query vector to compare against the vectors in the store.
   * @param k The number of top results to return.
   */
  protected async _queryVectors(query: number[], k: number) {
    return this.vectors
      .map(({ content, embedding, id }, index) => ({
        index,
        content,
        embedding,
        id,
        similarity: this.cosine(query, embedding)
      }))
      .sort((a, b) => (a.similarity > b.similarity ? -1 : 0))
      .slice(0, k)
  }

  /**
   * Returns the average of cosine distances between vectors a and b.
   *
   * @param a The first vector.
   * @param b The second vector.
   */
  private cosine(a: number[], b: number[]) {
    let [p, p2, q2] = [0, 0, 0]
    for (let i = 0; i < a.length; i++) {
      p += a[i] * b[i]
      p2 += a[i] * a[i]
      q2 += b[i] * b[i]
    }
    return p / (Math.sqrt(p2) * Math.sqrt(q2))
  }

  /**
   * Method to add documents to the memory vector store. It extracts the
   * text from each document, generates embeddings for them, and adds the
   * resulting vectors to the store.
   *
   * @param documents The array of `Document` instances to be added to the store.
   */
  async addDocuments(documents: Document[]) {
    const texts = documents.map(({ pageContent }) => pageContent)
    return this.addVectors(await this.embeddings.embedDocuments(texts), documents)
  }

  /**
   * Method to add vectors to the memory vector store. It creates
   * `MemoryVector` instances for each vector and document pair and adds
   * them to the store.
   *
   * @param vectors The array of vectors to be added to the store.
   * @param documents The array of `Document` instances corresponding to the vectors.
   * See {@link Document} for details.
   */
  async addVectors(vectors: number[][], documents: Document[]) {
    const memoryVectors = vectors.map((embedding, index) => ({
      content: documents[index].pageContent,
      embedding,
      id: documents[index].id
    }))
    this.vectors.push(...memoryVectors)
    if (this.vectors.length > 5000) {
      this.vectors.shift()
    }
  }

  /**
   * Method to perform a similarity search in the memory vector store. It
   * calculates the similarity between the query vector and each vector in
   * the store, sorts the results by similarity, and returns the top `k`
   * results along with their scores.
   *
   * @param query The query vector to compare against the vectors in the store.
   * @param topN The number of top results to return.
   */
  async similaritySearchVectorWithScore(query: number[], topN: number) {
    const result = await this._queryVectors(query, topN)
    return result.map((v) => [new Document({ pageContent: v.content, id: v.id }), v.similarity]) as [Document, number][]
  }
}
