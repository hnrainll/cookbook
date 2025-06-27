import base64
import binascii
import hashlib
import hmac
import random
import time
from urllib import parse

from loguru import logger


def _hmacsha1(base_string, key):
    hmac_hash = hmac.new(key.encode(), base_string.encode(), hashlib.sha1)
    return binascii.b2a_base64(hmac_hash.digest())[:-1]


def _hmac_sha1_modern(base_string, key):
    """现代化版本的 HMAC-SHA1 签名生成"""
    hmac_hash = hmac.new(
        key.encode('utf-8'),
        base_string.encode('utf-8'),
        hashlib.sha1
    )
    return base64.b64encode(hmac_hash.digest()).decode('utf-8')


def _normalized_url(url):
    # scheme, netloc, path = parse.urlparse(url)[:3]
    # return '{0}://{1}{2}'.format(scheme, netloc, path)

    parsed_url = parse.urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    return base_url


class OAuth(object):
    def __init__(
        self,
        consumer_key,
        consumer_secret,
        parameter_seperator=', ',
        realm='',
        last_ampersand=True,
    ):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.parameter_seperator = parameter_seperator
        self.realm = realm
        self.last_ampersand = last_ampersand

    def gen_authorization(self, request: dict, token: dict=None):
        oauth_data = self._authorize(request, token)
        authorization =  self._get_authorization(oauth_data)

        print(f"request is {request}")
        print(f"token is {token}")
        print(f"oauth_data is {oauth_data}")
        print(f"authorization is [{authorization}]")
        return authorization

    def _authorize(self, request: dict, token: dict=None):
        token = token or {}

        oauth_data = {
            'oauth_consumer_key': self.consumer_key,
            'oauth_signature_method': 'HMAC-SHA1',
            'oauth_timestamp': str(int(time.time())),
            'oauth_nonce': ''.join([str(random.randint(0, 9)) for _ in range(8)]),
            'oauth_version':  '1.0'
        }

        if 'key' in token:
            oauth_data['oauth_token'] = token['key']

        if 'data' not in request:
            request['data'] = {}

        oauth_data['oauth_signature'] = self._get_signature(request, token.get('secret', ''), oauth_data)
        return oauth_data

    def _get_authorization(self, oauth_data) -> str:
        parts = []

        if self.realm != '':
            parts.append(f'realm="{self.realm}"')

        for k, v in sorted(oauth_data.items()):
            if k.startswith(('oauth_', 'x_auth_')):
                parts.append(f'{k}="{self._escape(v)}"')

        return f'OAuth {self.parameter_seperator.join(parts)}'

        # authorization = 'OAuth '
        # if self.realm != '':
        #     authorization += 'realm="%s"' % self.realm
        #     authorization += self.parameter_seperator
        #
        # for k, v in sorted(oauth_data.items()):
        #     if k.startswith('oauth_') or k.startswith('x_auth_'):
        #         authorization += '%s="%s"%s' % (k, self._escape(v), self.parameter_seperator)
        #
        # return authorization[:-1]

    def _get_signature(self, request, token_secret, oauth_data):
        return _hmac_sha1_modern(self._get_base_string(request, oauth_data), self._get_signing_key(token_secret))

    def _get_base_string(self, request, oauth_data):
        logger.info(request)
        logger.info(oauth_data)

        query = parse.urlparse(request['url']).query

        logger.info(query)

        params = {}
        for k, v in parse.parse_qs(query).items():
            params[k] = v[0]

        logger.info(params)

        oauth_data.update(request['data'])
        oauth_data.update(params)

        logger.info(oauth_data)

        base_elements = (request['method'].upper(), _normalized_url(request['url']), self._get_query(oauth_data))

        logger.info(base_elements)

        base_string = '&'.join(self._escape(s) for s in base_elements)

        logger.info(f"_get_base_string is [{base_string}]")
        return base_string

    def _get_signing_key(self, token_secret=''):
        if (self.last_ampersand == False) & (token_secret == ''):
            return self._escape(self.consumer_secret)

        return self._escape(self.consumer_secret) + '&' + self._escape(token_secret)

    def _get_query(self, args, via='quote', safe='~'):
        # 1. 排序参数
        sorted_params = sorted(args.items())

        # 2. URL 编码并拼接
        encoded_params = []
        for k, v in sorted_params:
            encoded_params.append(f"{self._escape(str(k), via, safe)}={self._escape(str(v), via, safe)}")

        return "&".join(encoded_params)

        # return '&'.join('%s=%s' % (self._escape(str(k), via, safe), self._escape(str(v), via, safe)) for k, v in sorted(args.items()))

    def _escape(self, s: str, via='quote', safe='~'):
        # quote_via = getattr(parse, via)
        #
        # if isinstance(s, (int, float)):
        #     s = str(s)
        # if not isinstance(s, bytes):
        #     s = s.encode('utf-8')
        #
        # return quote_via(s, safe=safe)
        return parse.quote(s, safe=safe)

