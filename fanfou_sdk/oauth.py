import time
import hmac
import random
import hashlib
import binascii
from urllib import parse


def hmacsha1(base_string, key):
    hmac_hash = hmac.new(key.encode(), base_string.encode(), hashlib.sha1)
    return binascii.b2a_base64(hmac_hash.digest())[:-1]


class OAuth(object):
    def __init__(
        self,
        consumer_key,
        consumer_secret,
        parameter_seperator=',',
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
        return self._get_authorization(oauth_data)

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

    def _get_authorization(self, oauth_data):
        authorization = 'OAuth '
        if self.realm != '':
            authorization += 'realm="%s"' % self.realm
            authorization += self.parameter_seperator

        for k, v in sorted(oauth_data.items()):
            if k.startswith('oauth_') or k.startswith('x_auth_'):
                authorization += '%s="%s"%s' % (k, self._escape(v), self.parameter_seperator)

        return authorization[:-1]

    def _get_signature(self, request, token_secret, oauth_data):
        return hmacsha1(self._get_base_string(request, oauth_data), self._get_signing_key(token_secret))

    def _get_base_string(self, request, oauth_data):
        query = parse.urlparse(request['url'])[4:-1][0]
        params = {}
        for k, v in parse.parse_qs(query).items():
            params[k] = v[0]
        params.update(request['data'])
        oauth_data.update(params)
        base_elements = (request['method'].upper(), self._normalized_url(request['url']), self._get_query(oauth_data))
        base_string = '&'.join(self._escape(s) for s in base_elements)
        return base_string

    def _get_signing_key(self, token_secret=''):
        if (self.last_ampersand == False) & (token_secret == ''):
            return self._escape(self.consumer_secret)

        return self._escape(self.consumer_secret) + '&' + self._escape(token_secret)

    def _get_query(self, args, via='quote', safe='~'):
        return '&'.join('%s=%s' % (k, self._escape(v, via, safe)) for k, v in sorted(args.items()))

    def _escape(self, s, via='quote', safe='~'):
        quote_via = getattr(parse, via)

        if isinstance(s, (int, float)):
            s = str(s)
        if not isinstance(s, bytes):
            s = s.encode('utf-8')

        return quote_via(s, safe=safe)

    def _normalized_url(self, url):
        scheme, netloc, path = parse.urlparse(url)[:3]
        return '{0}://{1}{2}'.format(scheme, netloc, path)
