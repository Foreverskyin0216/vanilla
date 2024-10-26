import { type APIGatewayProxyEvent } from 'aws-lambda'
import { publishMessage } from '../services/sns'

export const handler = async (event: APIGatewayProxyEvent) => {
  await publishMessage(process.env.LINE_BOT_TOPIC, event.body)
  return { statusCode: 200, body: JSON.stringify({ message: 'Received' }) }
}
