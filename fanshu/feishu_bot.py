import json
from collections import OrderedDict

import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from loguru import logger

from fanshu.fanfou_api import gen_auth_url
from fanshu.fanfou_api import post_status


class OrderedDictDeduplicator:

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.messages = OrderedDict()  # 既有序又支持快速查找

    def add(self, message_id: str) -> bool:
        if message_id in self.messages:
            return False

        # 超出限制时删除最旧的
        if len(self.messages) >= self.max_size:
            self.messages.popitem(last=False)  # 删除最旧的

        self.messages[message_id] = True
        return True

    def exists(self, message_id: str) -> bool:
        return message_id in self.messages


def send_message(open_id: str, chat_message: str) -> CreateMessageResponse:
    content = json.dumps(
        {
            "text": chat_message
        }
    )

    request: CreateMessageRequest = (
        CreateMessageRequest.builder()
        .receive_id_type("open_id")
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(open_id)
            .msg_type("text")
            .content(content)
            .build()
        )
        .build()
    )

    # 使用OpenAPI发送消息
    # Use send OpenAPI to send messages
    # https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/create
    response: CreateMessageResponse = client.im.v1.message.create(request)

    return response


def reply_message(message_id: str, chat_message: str) -> ReplyMessageResponse:
    content = json.dumps(
        {
            "text": chat_message
        }
    )

    request: ReplyMessageRequest = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            ReplyMessageRequestBody.builder()
            .content(content)
            .msg_type("text")
            .build()
        )
        .build()
    )
    # 使用OpenAPI回复消息
    # Reply to messages using send OpenAPI
    # https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/reply
    response: ReplyMessageResponse = client.im.v1.message.reply(request)

    return response


# 注册接收消息事件，处理接收到的消息。
# Register event handler to handle received messages.
# https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/receive
def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    logger.info(f'[ do_p2_im_message_receive_v1 access ], data: {lark.JSON.marshal(data, indent=4)}')

    open_id = data.event.sender.sender_id.open_id
    message_type = data.event.message.message_type
    message_id = data.event.message.message_id
    # data.event.message.chat_type == "p2p":

    if dedup.exists(message_id):
        logger.debug(f"这条消息为重复消息: {message_id}")
        return

    if message_type == "text":
        content = json.loads(data.event.message.content)["text"]
        logger.info(content)
        # TODO：需要对消息长度做限制。

        ret = post_status(open_id, content)
        if ret:
            logger.info(json.dumps(ret, indent=2))

            dedup.add(message_id)
            reply_message(message_id, f"发送饭否成功\n\nhttps://fanfou.com/statuses/{ret['id']}")
        else:
            reply_message(message_id,"发送饭否失败")
    else:
        send_message(open_id,f"当前饭薯不支持该消息类型. message_type: {message_type}")


def do_p2_application_bot_menu_v6(data: lark.application.v6.P2ApplicationBotMenuV6) -> None:
    logger.info(f'[ do_p2_application_bot_menu_v6 access ], data: {lark.JSON.marshal(data, indent=4)}')

    event_key = data.event.event_key
    open_id = data.event.operator.operator_id.open_id

    if event_key == 'login':
        url = gen_auth_url(open_id)

        response = send_message(open_id, f"请点击如下链接并授权登录。\n{url}")
        if not response.success():
            raise Exception(
                f"client.im.v1.chat.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}"
            )


# 注册事件回调
# Register event handler.
event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
    .register_p2_application_bot_menu_v6(do_p2_application_bot_menu_v6)
    .build()
)


# 创建 LarkClient 对象，用于请求OpenAPI, 并创建 LarkWSClient 对象，用于使用长连接接收事件。
# Create LarkClient object for requesting OpenAPI, and create LarkWSClient object for receiving events using long connection.
client = lark.Client.builder().app_id(lark.APP_ID).app_secret(lark.APP_SECRET).build()
lark_ws_client = lark.ws.Client(
    lark.APP_ID,
    lark.APP_SECRET,
    event_handler=event_handler,
    log_level=lark.LogLevel.DEBUG,
)

dedup = OrderedDictDeduplicator()