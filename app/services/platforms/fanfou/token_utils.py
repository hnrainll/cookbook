
import os
import json
from loguru import logger


def save_request_token(oauth_token: str, token: dict, open_id: str):
    data = {
        'token': token,
        'open_id': open_id
    }

    try:
        with open(oauth_token, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存请求token失败: {e}")


def save_user_token(open_id: str, token: dict):
    user_token = {
        'token': token
    }

    try:
        with open(open_id, 'w', encoding='utf-8') as f:
            json.dump(user_token, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存用户token失败: {e}")


def load_token(file_name: str) -> dict| None:
    if os.path.exists(file_name):
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                token = json.load(f)
            return token
        except Exception as e:
            logger.warning(f"加载Token{file_name}失败: {e}")

    return None


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