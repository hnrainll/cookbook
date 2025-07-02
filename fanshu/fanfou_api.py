import json
import os

from fanfou_sdk import Fanfou
from loguru import logger


def gen_auth_url(open_id: str):
    ff = Fanfou(
        consumer_key=os.getenv('FANFOU_CONSUMER_KEY'),
        consumer_secret=os.getenv('FANFOU_CONSUMER_SECRET')
    )

    token, _ = ff.request_token()
    _save_request_token(ff.oauth_token, token, open_id)

    oauth_callback = os.getenv('FANFOU_OAUTH_CALLBACK')
    url = f"https://fanfou.com/oauth/authorize?oauth_token={ff.oauth_token}&oauth_callback={oauth_callback}"
    return url


def get_access_token(oauth_token: str):
    request_token = _load_token(oauth_token)

    if request_token:
        ff = Fanfou(
            consumer_key=os.getenv('FANFOU_CONSUMER_KEY'),
            consumer_secret=os.getenv('FANFOU_CONSUMER_SECRET')
        )

        open_id = request_token['open_id']
        token, response = ff.access_token(request_token['token'])

        remove_token(oauth_token)
        if token:
            _save_user_token(open_id, token)
            return "授权成功", open_id

    return "授权失败", None


def post_status(open_id: str, text: str):
    ret = None
    user_token = _load_token(open_id)

    if user_token:
        token = user_token['token']

        ff = Fanfou(
            consumer_key=os.getenv('FANFOU_CONSUMER_KEY'),
            consumer_secret=os.getenv('FANFOU_CONSUMER_SECRET'),
            oauth_token=token['oauth_token'],
            oauth_token_secret=token['oauth_token_secret']
        )

        content = {
            'status': text
        }

        ret, response = ff.post('/statuses/update', content)

    return ret


def remove_token(open_id: str) -> bool:
    file_path = open_id

    ret = False
    if os.path.exists(file_path) and os.path.isfile(file_path):
        try:
            os.remove(file_path)
            ret = True
            logger.info(f"文件 {file_path} 已成功删除")
        except Exception as e:
            logger.warning(f"删除文件 {file_path} 失败：{e}")
    else:
        logger.info(f"文件 {file_path} 不存在或不是文件")
    return ret


def _save_request_token(oauth_token: str, token: dict, open_id: str):
    data = {
        'token': token,
        'open_id': open_id
    }

    try:
        with open(oauth_token, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存请求token失败: {e}")


def _save_user_token(open_id: str, token: dict):
    user_token = {
        'token': token
    }

    try:
        with open(open_id, 'w', encoding='utf-8') as f:
            json.dump(user_token, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存用户token失败: {e}")


def _load_token(file_name: str) -> dict| None:
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                token = json.load(f)
            return token
        except Exception as e:
            logger.warning(f"加载Token{file_name}失败: {e}")

    return None
