import { Client } from '@evex/linejs'
import { HumanMessage } from '@langchain/core/messages'
import { MemorySaver } from '@langchain/langgraph'

import { createThread } from './ai'
import { chatGraph } from './chatGraph'
import { getThread, setThread, storeMessage } from './dynamoDB'
import { getParameter, setParameter } from './ssm'

export class Vanilla {
  client: Client
  graph: ReturnType<typeof chatGraph>
  name: string

  constructor(name = '香草') {
    this.client = new Client()
    this.graph = chatGraph(new MemorySaver())
    this.name = name

    this.client.on('ready', async () => {
      process.env.OPENAI_API_KEY = await getParameter('/vanilla/openai/apiKey')
      process.env.TAVILY_API_KEY = await getParameter('/vanilla/tavily/apiKey')
    })

    this.client.on('update:authtoken', async (authToken) => await setParameter('/vanilla/line/authToken', authToken))

    this.client.on(
      'square:message',
      async ({ author, content, contentMetadata, contentType, squareChatMid, react, reply }) => {
        try {
          if (contentType === 'NONE' && content) {
            const user = await author.displayName
            const question = content.replaceAll('@' + this.name, '').trim()
            await storeMessage({ thread_id: squareChatMid, content: user + '：' + question })

            if (contentMetadata?.MENTION && content.includes('@' + this.name)) {
              const response = await this.chat(squareChatMid, user + '：' + question)
              await reply(response)
            }
          }
        } catch (err) {
          await Promise.all([react(6), reply(`${err}`)])
        }
      }
    )
  }

  private async chat(id: string, question: string) {
    let thread = await getThread(id)
    if (!thread) {
      thread = { id, conversation_id: (await createThread()).id }
      await setThread(thread)
    }

    const { response } = await this.graph.invoke(
      {
        messages: [new HumanMessage(question)]
      },
      {
        configurable: { conversation_id: thread.conversation_id, thread_id: thread.id }
      }
    )

    return response
  }

  public async login() {
    const authToken = await getParameter('/vanilla/line/authToken')
    if (authToken) return this.client.login({ authToken, device: 'DESKTOPMAC', v3: true })

    const email = await getParameter('/vanilla/line/email')
    const password = await getParameter('/vanilla/line/password')

    return this.client.login({ email, password, device: 'DESKTOPMAC', v3: true })
  }
}
