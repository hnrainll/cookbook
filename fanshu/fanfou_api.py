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
    logger.info(token)

    _save_request_token(ff.oauth_token, token, open_id)

    url = f"https://fanfou.com/oauth/authorize?oauth_token={ff.oauth_token}&oauth_callback=https://wenhao.ink/fanshu/auth"
    logger.info(url)
    return url


def get_access_token(oauth_token: str):
    request_token = _load_token(oauth_token)
    logger.info(request_token)

    if request_token:
        ff = Fanfou(
            consumer_key=os.getenv('FANFOU_CONSUMER_KEY'),
            consumer_secret=os.getenv('FANFOU_CONSUMER_SECRET')
        )

        open_id = request_token['open_id']
        token, response = ff.access_token(request_token['token'])
        logger.info(token)
        logger.info(response)

        if token:
            _save_user_token(open_id, token)
            return "授权成功"

    return "授权失败"


def post_status(open_id: str, text: str):
    user_token = _load_token(open_id)
    logger.info(user_token)

    st = None
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

        st, response = ff.post('/statuses/update', content)

    return st


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