# -*- coding: utf-8 -*-

from urllib import parse

import requests
import json

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
        protocol='http:',
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
        self.api_endpoint = self.protocol + '//' + self.api_domain
        self.oauth_endpoint = self.protocol + '//' + self.oauth_domain

    def request_token(self):
        url = self.oauth_endpoint + '/oauth/request_token'
        authorization = self.o.gen_authorization({'url': url, 'method': 'GET'})
        r = requests.get(
            url,
            headers={
                'Authorization': authorization
            }
        )

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
            headers={
                'Authorization': authorization
            }
        )

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

    def get(self, uri, params={}):
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

        if r.status_code != 200:
            return None, r
        return r.json(), r

    def post(self, uri, params={}, files=None):
        url = self.api_endpoint + uri + '.json'
        token = {'key': self.oauth_token, 'secret': self.oauth_token_secret}
        is_upload = uri in ['/photos/upload', '/account/update_profile_image']
        authorization = self.o.gen_authorization(
            {'url': url, 'method': 'POST', 'data': {} if is_upload else params},
            token)

        headers = {
            'Authorization': authorization,
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        if is_upload:
            del headers['Content-Type']

        r = requests.post(
            url,
            headers=headers,
            data=params,
            files=files
        )

        print(r.request)
        print(r.request.headers)
        print(r.request.body)

        if r.status_code != 200:
            return None, r
        return r.json(), r
