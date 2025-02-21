import 'dotenv/config'
process.env.AWS_REGION = 'ap-southeast-2'
import { Vanilla } from './vanilla'

// Workaround for https://github.com/evex-dev/linejs/issues/45
process.on('uncaughtException', (error) => {
  if (error.name === 'InputBufferUnderrunError') console.error('InputBufferUnderrunError')
  else throw error
})
;(async () => await new Vanilla('vanilla').login())()
