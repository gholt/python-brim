"""A WSGI application that offers Basic Auth capabilities.

.. warning::

    This is an early version of this module. It has no tests, limited
    documentation, and is subject to major changes.

.. warning::

    This is HTTP Basic Auth, so the password will be transmitted in the
    clear. You definitely should be using SSL when using Basic Auth.

.. note::

    Requires the ``bcrypt`` package
    https://pypi.python.org/pypi/py-bcrypt

Configuration Options::

    [basic-auth]
    call = brim.wsgi_basic_auth.WSGIBasicAuth
    # auth_path = <path>
    #   The local file path to the auth details. This file should be
    #   plain text, one user per line, with each line a user name
    #   followed by whitespace and then the bcrypt password entry for
    #   the user. You can obtain the bcrypt password entry with the
    #   following:
    #       $ python -c '
    #       > import bcrypt
    #       > print bcrypt.hashpw("secret", bcrypt.gensalt())'
    #   The file will automatically be reloaded if changed within five
    #   minutes.
"""
"""Copyright and License.

Copyright 2014 Gregory Holt

Licensed under the Apache License, Version 2.0 (the "License"); you may
not use this file except in compliance with the License. You may obtain
a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from hashlib import sha1
from os.path import getmtime
from time import time

from brim.http import quote

try:
    from bcrypt import hashpw
except ImportError:
    hashpw = None


class WSGIBasicAuth(object):
    """
    A WSGI application that offers Basic Auth capabilities.

    See :py:mod:`brim.wsgi_basic_auth` for more information.

    :param name: The name of the app.
    :param parsed_conf: The conf result from :py:meth:`parse_conf`.
    :param next_app: The next WSGI app in the chain.
    """

    def __init__(self, name, parsed_conf, next_app):
        self.name = name
        """The name of the app."""
        self.next_app = next_app
        """The next WSGI app in the chain."""
        self.auth_path = parsed_conf['auth_path']
        """The auth file path; see :py:mod:`brim.wsgi_basic_auth`"""
        self.auth_path_check_mtime_interval = 300
        self.auth_path_last_mtime = getmtime(self.auth_path)
        self.next_time_to_check_auth_path_mtime = \
            time() + self.auth_path_check_mtime_interval
        self.no_memcache_log_interval = 900
        self.next_time_to_log_no_memcache = 0
        self.unauthed_paths = ['/favicon.ico']

    def _check_username_password(self, env, username, password):
        memcache = env.get('memcache')
        if not memcache and time() >= self.next_time_to_log_no_memcache:
            self.next_time_to_log_no_memcache = \
                time() + self.no_memcache_log_interval
            env['brim.logger'].warning(
                "Authorization with no memcache['env'] will slow down every "
                "request")
        key = '/wsgi_basic_auth/%s/%s' % (
            quote(username, safe=''), sha1(password).hexdigest())
        if memcache:
            try:
                memcached_value = memcache.get(key)
            except Exception as err:
                env['brim.logger'].warning(
                    'Authorization problem accessing memcache for username '
                    '%r: %s' % (username, err))
            else:
                if memcached_value:
                    try:
                        memcached_username, memcached_mtime = memcached_value
                    except (TypeError, ValueError) as err:
                        env['brim.logger'].warning(
                            'Authorization invalid memcache value %r for '
                            'username %r: %s' %
                            (memcached_value.encode('utf8'), username, err))
                    else:
                        if time() >= self.next_time_to_check_auth_path_mtime:
                            self.auth_path_last_mtime = getmtime(
                                self.auth_path)
                            self.next_time_to_check_auth_path_mtime = \
                                time() + self.auth_path_check_mtime_interval
                            env['brim.logger'].debug(
                                'Authorization read mtime %s for %r' %
                                (self.auth_path_last_mtime, self.auth_path))
                        if memcached_username == username:
                            if memcached_mtime == self.auth_path_last_mtime:
                                env['REMOTE_USER'] = username
                                del env['HTTP_AUTHORIZATION']
                                env['brim.logger'].debug(
                                    'Authorization for username %r validated '
                                    'by memcache' % username)
                            else:
                                env['brim.logger'].debug(
                                    'Authorization memcached value was from '
                                    'different mtime: %s != %s' % (
                                        memcached_mtime,
                                        self.auth_path_last_mtime))
                        else:
                            env['brim.logger'].debug(
                                'Authorization memcached value was for '
                                'different username: %r != %r' %
                                (memcached_username, username))
        if not env.get('REMOTE_USER'):
            with open(self.auth_path, 'r') as fp:
                for line in fp:
                    line = line.split(None, 1)
                    if len(line) == 2 and line[0] == username:
                        bcrypted = line[1].strip()
                        if hashpw(password, bcrypted) == bcrypted:
                            env['REMOTE_USER'] = username
                            del env['HTTP_AUTHORIZATION']
                            env['brim.logger'].debug(
                                'Authorization for username %r validated by '
                                '%r' % (username, self.auth_path))
                            if memcache:
                                memcached_value = (
                                    username, self.auth_path_last_mtime)
                                memcache.set(key, memcached_value)
                                env['brim.logger'].debug(
                                    'Authorization memcached %r' %
                                    (memcached_value,))
                        else:
                            env['brim.logger'].debug(
                                'Authorization failure for %r' % username)
                        break
                else:
                    env['brim.logger'].debug(
                        'Authorization unknown username %r' % username)

    def __call__(self, env, start_response):
        """Handles incoming requests, adhering to any basic auth settings.

        :param env: The WSGI env as per the spec.
        :param start_response: The WSGI start_response as per the spec.
        :returns: Calls *start_response* and returns an iterable as per
            the WSGI spec.
        """
        if env['PATH_INFO'] in self.unauthed_paths:
            return self.next_app(env, start_response)
        username = ''
        env['REMOTE_USER'] = ''
        auth_value = env.get('HTTP_AUTHORIZATION')
        if auth_value:
            auth_value = auth_value.split(' ', 1)
            if len(auth_value) != 2:
                env['brim.logger'].debug(
                    'Authorization value invalid %r' %
                    env.get('HTTP_AUTHORIZATION'))
            elif auth_value[0].lower() != 'basic':
                env['brim.logger'].debug(
                    'Authorization type unknown %r from %r' %
                    (auth_value[0], env.get('HTTP_AUTHORIZATION')))
            else:
                auth_value = auth_value[1].strip()
                try:
                    auth_value = auth_value.decode('base64')
                except Exception:
                    env['brim.logger'].debug(
                        'Authorization could not base64 decode %r from %r' %
                        (auth_value, env.get('HTTP_AUTHORIZATION')))
                else:
                    auth_value = auth_value.split(':', 1)
                    if len(auth_value) != 2:
                        env['brim.logger'].debug(
                            'Authorization basic value invalid %r from %r' %
                            (auth_value, env.get('HTTP_AUTHORIZATION')))
                    else:
                        username, password = (
                            v.encode('utf8') for v in auth_value)
                        self._check_username_password(env, username, password)
        if not env.get('REMOTE_USER'):
            env['REMOTE_USER'] = username  # For logging purposes
            start_response(
                '401 Not Authorized',
                [('Content-Length', '0'),
                 ('WWW-Authenticate', 'Basic realm="WSGIBasicAuth"')])
            return ''
        env['brim.authenticated_user'] = env['REMOTE_USER']
        return self.next_app(env, start_response)

    @classmethod
    def parse_conf(cls, name, conf):
        """Translates the overall server configuration.

        The conf is translated into an app-specific configuration dict
        suitable for passing as ``parsed_conf`` in the
        :py:class:`WSGIBasicAuth` constructor.

        See the overall docs of :py:mod:`brim.wsgi_basic_auth` for
        configuration options.

        :param name: The name of the app, indicates the app's section in
            the overall configuration for the server.
        :param conf: The :py:class:`brim.conf.Conf` instance
            representing the overall configuration of the server.
        :returns: A dict suitable for passing as ``parsed_conf`` in the
            :py:class:`WSGIBasicAuth` constructor.
        """
        if not hashpw:
            raise Exception(
                'bcrypt does not seem to be installed as is needed for the '
                'WSGIBasicAuth app.')
        parsed_conf = {'auth_path': conf.get_path(name, 'auth_path')}
        if not parsed_conf['auth_path']:
            raise Exception('[%s] auth_path must be set' % name)
        return parsed_conf
