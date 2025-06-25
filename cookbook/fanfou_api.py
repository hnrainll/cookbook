from fanfou_sdk import Fanfou

from loguru import logger

import os


def gen_fanfou_auth_url():
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


    # const url = `https://m.fanfou.com/oauth/authorize?oauth_token=${ff.oauthToken}&oauth_callback=https://labs.1a23.com/fanfou_auth`;
