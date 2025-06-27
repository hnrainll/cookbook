import json
from urllib import parse

import requests
from loguru import logger

from . import oauth


class Fanfou:
    def __init__(
        self,
        consumer_key='',
        consumer_secret='',
        oauth_token='',
        oauth_token_secret='',
        username='',
        password='',
        api_domain='api.fanfou.com',
        oauth_domain='fanfou.com',
        protocol='http',
    ):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.oauth_token = oauth_token
        self.oauth_token_secret = oauth_token_secret
        self.username = username
        self.password = password
        self.api_domain = api_domain
        self.oauth_domain = oauth_domain
        self.protocol = protocol
        self.o = oauth.OAuth(self.consumer_key, self.consumer_secret)
        self.api_endpoint = self.protocol + '://' + self.api_domain
        self.oauth_endpoint = self.protocol + '://' + self.oauth_domain

    def request_token(self):
        url = self.oauth_endpoint + '/oauth/request_token'
        authorization = self.o.gen_authorization({'url': url, 'method': 'GET'})
        r = requests.get(
            url,
            headers={'Authorization': authorization}
        )

        _log_request_to_json(r)

        if r.status_code != 200:
            return None, r

        token = parse.parse_qs(r.text)
        self.oauth_token = token['oauth_token'][0]
        self.oauth_token_secret = token['oauth_token_secret'][0]
        return {'oauth_token': self.oauth_token, 'oauth_token_secret': self.oauth_token_secret}, r

    def access_token(self, token):
        url = self.oauth_endpoint + '/oauth/access_token'
        authorization = self.o.gen_authorization(
            {'url': url, 'method': 'GET'},
            {'key': token['oauth_token'], 'secret': token['oauth_token_secret']}
        )

        r = requests.get(
            url,
            headers={'Authorization': authorization}
        )

        _log_request_to_json(r)

        if r.status_code != 200:
            return None, r

        token = parse.parse_qs(r.text)
        self.oauth_token = token['oauth_token'][0]
        self.oauth_token_secret = token['oauth_token_secret'][0]
        return {'oauth_token': self.oauth_token, 'oauth_token_secret': self.oauth_token_secret}, r

    def xauth(self):
        url = self.oauth_endpoint + '/oauth/access_token'
        params = {
            'x_auth_mode': 'client_auth',
            'x_auth_password': self.password,
            'x_auth_username': self.username
        }
        authorization = self.o.gen_authorization({'url': url, 'method': 'POST'})
        r = requests.post(
            url,
            headers={
                'Authorization': authorization,
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            data=params
        )

        if r.status_code != 200:
            return None, r

        token = parse.parse_qs(r.text)
        self.oauth_token = token['oauth_token'][0]
        self.oauth_token_secret = token['oauth_token_secret'][0]
        return {'oauth_token': self.oauth_token, 'oauth_token_secret': self.oauth_token_secret}, r

    def get(self, uri, params=None):
        params = params or {}

        url = self.api_endpoint + uri + '.json'
        if bool(params):
            url += '?%s' % parse.urlencode(params)

        token = {'key': self.oauth_token, 'secret': self.oauth_token_secret}
        authorization = self.o.gen_authorization({'url': url, 'method': 'GET'}, token=token)
        r = requests.get(
            url,
            headers={
                'Authorization': authorization,
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        )

        _log_request_to_json(r)

        if r.status_code != 200:
            return None, r
        return r.json(), r

    def post(self, uri: str, params: dict=None):
        params = params or {}
        url = f"{self.api_endpoint}{uri}.json"

        authorization = self.o.gen_authorization(
            {'url': url, 'method': 'POST', 'data': params},
            {'key': self.oauth_token, 'secret': self.oauth_token_secret}
        )

        headers = {
            'Authorization': authorization,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        r = requests.post(
            url,
            headers=headers,
            data=params
        )

        _log_request_to_json(r)

        if r.status_code != 200:
            return None, r
        return r.json(), r


def _log_request_to_json(response: requests.models.Response):
    try:
        data = {
            "request": {
                "url": response.request.url,
                "method": response.request.method,
                "headers": dict(response.request.headers),  # 转换为普通字典
                "body": response.request.body,
            },
            "response": {
                "status_code": response.status_code,
                "reason": response.reason,
                "headers": dict(response.headers),
            }
        }

        logger.info(json.dumps(data, indent=2))
        logger.info(f"response.json = {response.json()}")
    except Exception as e:
        logger.info(f"_log_request_to_json:{e}")