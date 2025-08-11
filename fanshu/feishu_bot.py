import json
from collections import OrderedDict

import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from loguru import logger

from fanshu import fanfou_api


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


def send_message(open_id: str, text: str) -> CreateMessageResponse:
    content = json.dumps(
        {
            "text": text
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


def reply_message(message_id: str, text: str) -> ReplyMessageResponse:
    content = json.dumps(
        {
            "text": text
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


def get_feishu_image_data(message_id: str, file_key: str) -> bytes | None:
    try:
        request: GetMessageResourceRequest = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(file_key) \
            .type("image") \
            .build()

        # 发起请求
        response: GetMessageResourceResponse = client.im.v1.message_resource.get(request)

        logger.info(response)

        if response.code == 0:
            return response.file.read()
        else:
            logger.error(f"下载飞书图片失败: {response.msg}")
            return None
    except Exception as e:
        logger.error(f"下载飞书图片异常: {e}")
        return None


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
        
        if len(content) > 140:
            reply_message(message_id, "消息长度大于140，无法发送。")
            return

        if content == '/login':
            fanfou_login(open_id)
        elif content == '/logout':
            fanfou_logout(open_id)
        else:
            fanfou_post_text(open_id, message_id, content)
    elif message_type == "image":
        content = json.loads(data.event.message.content)
        image_key = content.get("image_key")

        if image_key:
            image_data = get_feishu_image_data(message_id, image_key)
            if image_data:
                fanfou_post_photo(open_id, message_id, image_data)
            else:
                reply_message(message_id, "下载图片失败，无法发送。")
        else:
            reply_message(message_id, "未找到图片文件。")
    elif message_type == "post":
        content = json.loads(data.event.message.content)
        logger.debug(lark.JSON.marshal(content, indent=4))

        image_key, text = _extract_img_and_first_text_group(content)

        if image_key:
            image_data = get_feishu_image_data(message_id, image_key)
            if image_data:
                fanfou_post_photo(open_id, message_id, image_data, text)
            else:
                reply_message(message_id, "下载图片失败，无法发送。")
        elif text:
            if len(text) > 140:
                reply_message(message_id, "消息长度大于140，无法发送。")
            else:
                fanfou_post_text(open_id, message_id, text)
        else:
            reply_message(message_id, "发送富文本内容失败。")
    else:
        send_message(open_id,f"当前饭薯不支持该消息类型. message_type: {message_type}")


def fanfou_login(open_id):
    url = fanfou_api.gen_auth_url(open_id)
    send_message(open_id, f"请点击如下链接并授权登录。\n{url}")


def fanfou_logout(open_id):
    ret = fanfou_api.remove_token(open_id)
    if ret:
        send_message(open_id, "登出成功")
    else:
        send_message(open_id, "登出失败")


def fanfou_post_text(open_id, message_id, content):
    ret = fanfou_api.post_text(open_id, content)
    if ret:
        logger.info(json.dumps(ret, indent=2))

        dedup.add(message_id)
        reply_message(message_id, f"消息发送成功\n\nhttps://fanfou.com/statuses/{ret['id']}")
    else:
        reply_message(message_id, "消息发送失败")


def fanfou_post_photo(open_id, message_id, image_data, text: str=None):
    ret = fanfou_api.post_photo(open_id, image_data, text)

    if ret:
        logger.info(json.dumps(ret, indent=2))

        dedup.add(message_id)
        reply_message(message_id, f"图片发送成功\n\nhttps://fanfou.com/statuses/{ret['id']}")
    else:
        reply_message(message_id, "图片发送失败")


def _extract_img_and_first_text_group(data, separator=''):
    """
    从JSON数据中提取第一个img标签的image_key值和第一个包含text的列表中的所有text值

    Args:
        data: dict 或 JSON字符串
        separator: text值之间的分隔符，默认为空字符串（直接连接）

    Returns:
        tuple: (image_key, combined_text_from_first_group)
               - image_key: 第一个img标签的image_key值，如果没有则为None
               - combined_text_from_first_group: 第一个包含text的列表中所有text值合并后的字符串
    """
    # 如果输入是字符串，先解析为字典
    if isinstance(data, str):
        data = json.loads(data)

    content = data.get('content', [])

    first_image_key = None
    first_text_group = []
    first_text_group_found = False

    # 遍历content中的每个列表
    for item_list in content:
        current_list_texts = []

        # 一次遍历同时处理img和text
        for item in item_list:
            tag = item.get('tag')

            # 查找第一个img
            if tag == 'img' and first_image_key is None:
                first_image_key = item.get('image_key')

            # 收集当前列表中的text（如果还没找到第一个text组）
            elif tag == 'text' and not first_text_group_found:
                text_value = item.get('text')
                if text_value:
                    current_list_texts.append(text_value)

        # 如果当前列表包含text且还没找到第一个text组，就是我们要的
        if current_list_texts and not first_text_group_found:
            first_text_group = current_list_texts
            first_text_group_found = True

        # 如果已经找到了img和第一个text组，可以提前退出
        if first_image_key is not None and first_text_group_found:
            break

    # 合并第一个text组的所有text值
    combined_text = separator.join(first_text_group) if first_text_group else ''

    return first_image_key, combined_text


# 注册事件回调
# Register event handler.
event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
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