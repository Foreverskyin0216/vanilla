import 'dotenv/config'
import { ChatBot } from './bot'
;(async () => {
  const vanilla = new ChatBot(process.env.CATGIRL_NAME || '香草')
  await vanilla.serve()
})()
