"""A WSGI application that simply serves up files from the file system.

.. warning::

    This is an early version of this module. It has no tests, limited
    documentation, and is subject to major changes.

Configuration Options::

    [wsgi_fs]
    call = brim.wsgi_fs.WSGIFS
    # path = <path>
    #   The request path to match and serve; any paths that do not begin
    #   with this value will be passed on to the next WSGI app in the
    #   chain. Default: /
    # serve_path = <path>
    #   The local file path containing files to serve.
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
import mimetypes
import os
import time

from brim import http


MONTH_ABR = (
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct',
    'Nov', 'Dec')
WEEKDAY_ABR = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


def http_date_time(when):
    """Returns a date and time formatted as per HTTP RFC 2616."""
    gmtime = time.gmtime(when)
    return '%s, %02d %3s %4d %02d:%02d:%02d GMT' % (
        WEEKDAY_ABR[gmtime.tm_wday], gmtime.tm_mday,
        MONTH_ABR[gmtime.tm_mon - 1], gmtime.tm_year, gmtime.tm_hour,
        gmtime.tm_min, gmtime.tm_sec)


def _openiter(path, chunk_size, total_size):
    left = total_size
    with open(path, 'rb') as source:
        while True:
            chunk = source.read(min(chunk_size, left))
            if not chunk:
                break
            left -= len(chunk)
            yield chunk
    if left >= chunk_size:
        chunk = ' ' * chunk_size
        while left >= chunk_size:
            left -= chunk_size
            yield chunk
    if left:
        yield ' ' * left


class WSGIFS(object):
    """A WSGI app for serving up files from the file system.

    See :py:mod:`brim.wsgi_fs` for more information.

    :param name: The name of the app.
    :param parsed_conf: The conf result from :py:meth:`parse_conf`.
    :param next_app: The next WSGI app in the chain.
    """

    def __init__(self, name, parsed_conf, next_app):
        self.name = name
        """The name of the app."""
        self.next_app = next_app
        """The next WSGI app in the chain."""
        self.path = parsed_conf['path']
        """The request path to match and serve.

        Any paths that do not begin with this value will be passed on to
        the next WSGI app in the chain. The attribute will have leading
        and trailing foward slashes removed.
        """
        self.serve_path = parsed_conf['serve_path']
        """The local file path containing files to serve."""

    def __call__(self, env, start_response):
        """Handles incoming WSGI requests.

        Requests that start with the configured path simply serve up any
        files under the configured location on the file system. Other
        requests are passed on to the next WSGI app in the chain.

        :param env: The WSGI env as per the spec.
        :param start_response: The WSGI start_response as per the spec.
        :returns: Calls *start_response* and returns an iterable as per
            the WSGI spec.
        """
        path = os.path.normpath(env['PATH_INFO'].strip('/'))
        if path == self.path:
            path = '.'
        elif path.startswith(self.path + '/'):
            path = path[len(self.path) + 1:]
            if not path:
                path = '.'
        elif self.path:
            return self.next_app(env, start_response)
        if path == '..' or path.startswith('..' + os.path.sep):
            return http.HTTPForbidden()(env, start_response)
        path = os.path.join(self.serve_path, path)
        if not os.path.exists(path):
            return http.HTTPNotFound()(env, start_response)
        if os.path.isdir(path):
            if not env['PATH_INFO'].endswith('/'):
                return http.HTTPMovedPermanently(
                    headers={'Location': env['PATH_INFO'] + '/'})(
                    env, start_response)
            path = os.path.join(path, 'index.html')
        content_type = mimetypes.guess_type(path)[0] or \
            'application/octet-stream'
        stat = os.stat(path)
        if not stat.st_size:
            start_response(
                '204 No Content',
                [('Content-Length', '0'), ('Content-Type', content_type)])
        start_response(
            '200 OK',
            [('Content-Length', str(stat.st_size)),
             ('Content-Type', content_type),
             ('Last-Modified',
              http_date_time(min(stat.st_mtime, time.time())))])
        if env['REQUEST_METHOD'] == 'HEAD':
            return ''
        return _openiter(path, 65536, stat.st_size)

    @classmethod
    def parse_conf(cls, name, conf):
        """Translates the overall server configuration.

        The conf is translated into an app-specific configuration dict
        suitable for passing as ``parsed_conf`` in the
        :py:class:`WSGIFS` constructor.

        See the overall docs of :py:mod:`brim.wsgi_fs` for
        configuration options.

        :param name: The name of the app, indicates the app's section in
            the overall configuration for the server.
        :param conf: The :py:class:`brim.conf.Conf` instance
            representing the overall configuration of the server.
        :returns: A dict suitable for passing as ``parsed_conf`` in the
            :py:class:`WSGIFS` constructor.
        """
        parsed_conf = {
            'path': conf.get(name, 'path', '/').strip('/'),
            'serve_path': conf.get_path(name, 'serve_path')}
        if not parsed_conf['serve_path']:
            raise Exception('[%s] serve_path must be set' % name)
        return parsed_conf
