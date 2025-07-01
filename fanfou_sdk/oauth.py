import base64
import hashlib
import hmac
import random
import string
import time
from urllib import parse


def _hmac_sha1_modern(base_string, key):
    """现代化版本的 HMAC-SHA1 签名生成"""
    hmac_hash = hmac.new(
        key.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha1
    )
    return base64.b64encode(hmac_hash.digest()).decode('utf-8')


def _normalized_url(url):
    parsed_url = parse.urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    return base_url


def _escape(text):
    return parse.quote(str(text), safe='')


def _get_query(args):
    sorted_params = sorted(args.items())
    encoded_params = [f"{_escape(k)}={_escape(v)}" for k, v in sorted_params]

    return "&".join(encoded_params)


def _get_base_string(request, oauth_data):
    query = parse.urlparse(request['url']).query

    params = {}
    for k, v in parse.parse_qs(query).items():
        params[k] = v[0]

    oauth_data.update(params)
    oauth_data.update(request['data'])

    base_elements = (request['method'].upper(), _normalized_url(request['url']), _get_query(oauth_data))
    base_string = '&'.join(_escape(s) for s in base_elements)
    return base_string


def _get_signing_key(consumer_secret: str, token_secret: str= ''):
    signing_key = f"{_escape(consumer_secret)}&{_escape(token_secret)}"
    return signing_key


class OAuth(object):

    def __init__(
        self,
        consumer_key,
        consumer_secret,
        parameter_seperator=',',
    ):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.parameter_seperator = parameter_seperator

    def gen_authorization(self, request: dict, token: dict=None):
        oauth_data = self._authorize(request, token)
        authorization =  self._get_authorization(oauth_data)

        return authorization

    def _authorize(self, request: dict, token: dict=None):
        token = token or {}

        oauth_data = {
            'oauth_consumer_key': self.consumer_key,
            'oauth_signature_method': 'HMAC-SHA1',
            'oauth_timestamp': str(int(time.time())),
            'oauth_nonce': ''.join(random.choices(string.ascii_letters + string.digits, k=32)),
            'oauth_version':  '1.0'
        }

        if 'key' in token:
            oauth_data['oauth_token'] = token['key']

        if 'data' not in request:
            request['data'] = {}

        oauth_data['oauth_signature'] = self._get_signature(request, oauth_data, token.get('secret', ''))
        return oauth_data

    def _get_authorization(self, oauth_data) -> str:
        parts = []

        for k, v in sorted(oauth_data.items()):
            if k.startswith(('oauth_', 'x_auth_')):
                parts.append(f'{_escape(k)}="{_escape(v)}"')

        return f'OAuth {self.parameter_seperator.join(parts)}'


    def _get_signature(self, request, oauth_data, token_secret):
        base_string = _get_base_string(request, oauth_data)
        key_string = _get_signing_key(self.consumer_secret, token_secret)

        return _hmac_sha1_modern(base_string, key_string)


