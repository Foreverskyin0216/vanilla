import { messagingApi } from '@line/bot-sdk'
import { getParameter } from '../services/ssm'
import { logger } from '../utils/logger'

export type Message = messagingApi.ImageMessage | messagingApi.TextMessage

export const reply = async (replyToken: string, messages: Message[]) => {
  try {
    const client = new messagingApi.MessagingApiClient({
      channelAccessToken: await getParameter('/vanilla/line/channelAccessToken')
    })
    return client.replyMessage({ replyToken, messages })
  } catch (error) {
    logger.error(error)
    throw error
  }
}

export const getProfile = async (groupId: string, userId: string) => {
  try {
    const client = new messagingApi.MessagingApiClient({
      channelAccessToken: await getParameter('/vanilla/line/channelAccessToken')
    })
    return client.getGroupMemberProfile(groupId, userId)
  } catch (error) {
    logger.error(error)
    throw error
  }
}
