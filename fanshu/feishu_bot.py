import json
from collections import OrderedDict

import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from loguru import logger

from fanshu import fanfou_api
from fanshu import image_utils
from fanshu import feishu_utils
from fanshu.database import message_db


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
    image_data = None

    try:
        request: GetMessageResourceRequest = GetMessageResourceRequest.builder() \
            .message_id(message_id) \
            .file_key(file_key) \
            .type("image") \
            .build()

        # 发起请求
        response: GetMessageResourceResponse = client.im.v1.message_resource.get(request)

        if response.code == 0:
            image_data = image_utils.compress_image_advanced(response.file.read())
        else:
            logger.error(f"下载飞书图片失败: {response.msg}")
    except Exception as e:
        logger.error(f"下载飞书图片异常: {e}")

    return image_data


# 注册接收消息事件，处理接收到的消息。
# Register event handler to handle received messages.
# https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/receive
def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    logger.info(f'[ do_p2_im_message_receive_v1 access ], data: {lark.JSON.marshal(data, indent=4)}')

    open_id = data.event.sender.sender_id.open_id
    message_type = data.event.message.message_type
    message_id = data.event.message.message_id

    if dedup.exists(message_id):
        logger.debug(f"这条消息为重复消息: {message_id}")
        return

    dedup.add(message_id)
    if message_type == "text":
        content = json.loads(data.event.message.content)["text"]
        
        if len(content) > 140:
            reply_message(message_id, "消息长度大于140，无法发送。")
            return

        if content == '/login':
            # 保存登录命令到数据库
            message_db.save_message(message_id, open_id, "text", content=content)
            fanfou_login(open_id)
        elif content == '/logout':
            # 保存登出命令到数据库
            message_db.save_message(message_id, open_id, "text", content=content)
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
                # 保存下载失败的图片消息到数据库
                message_db.save_message(message_id, open_id, "image", content="下载失败")
                reply_message(message_id, "下载图片失败，无法发送。")
        else:
            # 保存未找到文件的消息到数据库
            message_db.save_message(message_id, open_id, "image", content="未找到文件")
            reply_message(message_id, "未找到图片文件。")
    elif message_type == "post":
        content = json.loads(data.event.message.content)
        logger.debug(lark.JSON.marshal(content, indent=4))

        image_key, text = feishu_utils.extract_img_and_first_text_group(content)

        if image_key:
            image_data = get_feishu_image_data(message_id, image_key)
            if image_data:
                fanfou_post_photo(open_id, message_id, image_data, text)
            else:
                # 保存下载失败的富文本图片消息到数据库
                message_db.save_message(message_id, open_id, "post", content=json.dumps(content))
                reply_message(message_id, "下载图片失败，无法发送。")
        elif text:
            if len(text) > 140:
                # 保存超长文本到数据库
                message_db.save_message(message_id, open_id, "post", content=text)
                reply_message(message_id, "消息长度大于140，无法发送。")
            else:
                fanfou_post_text(open_id, message_id, text)
        else:
            # 保存富文本消息到数据库
            message_db.save_message(message_id, open_id, "post", content=json.dumps(content))
            reply_message(message_id, "发送富文本内容失败。")
    else:
        # 保存不支持的消息类型到数据库
        message_db.save_message(message_id, open_id, message_type)
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
    # 保存消息到数据库
    message_db.save_message(message_id, open_id, "text", content=content)
    
    ret = fanfou_api.post_text(open_id, content)
    if ret:
        logger.info(json.dumps(ret, indent=2))
        # 更新数据库中的饭否响应
        message_db.update_fanfou_response(message_id, ret.get('id'), ret)
        reply_message(message_id, f"消息发送成功\n\nhttps://fanfou.com/statuses/{ret['id']}")
    else:
        # 更新数据库中的失败状态
        message_db.update_fanfou_response(message_id, None, {"error": "发送失败"})
        reply_message(message_id, "消息发送失败")


def fanfou_post_photo(open_id, message_id, image_data, text: str=None):
    # 保存消息到数据库
    message_db.save_message(message_id, open_id, "image", content=text, image_data=image_data)
    
    ret = fanfou_api.post_photo(open_id, image_data, text)

    if ret:
        logger.info(json.dumps(ret, indent=2))
        # 更新数据库中的饭否响应
        message_db.update_fanfou_response(message_id, ret.get('id'), ret)
        reply_message(message_id, f"图片发送成功\n\nhttps://fanfou.com/statuses/{ret['id']}")
    else:
        # 更新数据库中的失败状态
        message_db.update_fanfou_response(message_id, None, {"error": "图片发送失败"})
        reply_message(message_id, "图片发送失败")


# 注册事件回调
# Register event handler.
feishu_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
    .build()
)


# 创建 LarkClient 对象，用于请求OpenAPI, 并创建 LarkWSClient 对象，用于使用长连接接收事件。
# Create LarkClient object for requesting OpenAPI, and create LarkWSClient object for receiving events using long connection.
client = lark.Client.builder().app_id(lark.APP_ID).app_secret(lark.APP_SECRET).build()

# lark_ws_client = lark.ws.Client(
#     lark.APP_ID,
#     lark.APP_SECRET,
#     event_handler=event_handler,
#     log_level=lark.LogLevel.DEBUG,
# )

dedup = OrderedDictDeduplicator()