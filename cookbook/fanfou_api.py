import os

from fanfou_sdk import Fanfou
from loguru import logger

ff: Fanfou | None = None

def gen_auth_url():
    global ff

    ff = Fanfou(
        consumer_key=os.getenv('FANFOU_CONSUMER_KEY'),
        consumer_secret=os.getenv('FANFOU_CONSUMER_SECRET')
    )

    result, response = ff.request_token()

    logger.info(result)
    logger.info(type(response))
    logger.info(response)

    url = f"https://fanfou.com/oauth/authorize?oauth_token={ff.oauth_token}&oauth_callback=https://wenhao.ink/fanshu/auth"
    print(url)
    return url

def get_access_token():
    token = {
        'oauth_token': ff.oauth_token,
        'oauth_token_secret': ff.oauth_token_secret
    }

    result, response = ff.access_token(token)
    logger.info(result)
    logger.info(response)