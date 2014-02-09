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
from cgi import escape

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
            dirpath = path
            path = os.path.join(path, 'index.html')
            if not os.path.exists(path):
                return self.listing(dirpath, env, start_response)
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

    def listing(self, path, env, start_response):
        if not path.startswith(self.serve_path + '/'):
            return HTTPForbidden()(env, start_response)
        rpath = '/' + self.path + '/' + path[len(self.serve_path):]
        epath = escape(rpath)
        body = (
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 '
            'Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">\n'
            '<html>\n'
            ' <head>\n'
            '  <title>Listing of %s</title>\n'
            '  <style type="text/css">\n'
            '   h1 {font-size: 1em; font-weight: bold;}\n'
            '   th {text-align: left; padding: 0px 1em 0px 1em;}\n'
            '   td {padding: 0px 1em 0px 1em;}\n'
            '   a {text-decoration: none;}\n'
            '  </style>\n'
            ' </head>\n'
            ' <body>\n'
            '  <h1 id="title">Listing of %s</h1>\n'
            '  <table id="listing">\n'
            '   <tr id="heading">\n'
            '    <th class="colname">Name</th>\n'
            '    <th class="colsize">Size</th>\n'
            '    <th class="coldate">Date</th>\n'
            '   </tr>\n' % (epath, epath))
        if env['PATH_INFO'].count('/') > 1:
            body += (
                '   <tr id="parent" class="item">\n'
                '    <td class="colname"><a href="../">../</a></td>\n'
                '    <td class="colsize">&nbsp;</td>\n'
                '    <td class="coldate">&nbsp;</td>\n'
                '   </tr>\n')
        listing = sorted(os.listdir(path))
        for item in listing:
            itempath = os.path.join(path, item)
            if os.path.isdir(itempath):
                body += (
                    '   <tr class="item subdir">\n'
                    '    <td class="colname"><a href="%s">%s</a></td>\n'
                    '    <td class="colsize">&nbsp;</td>\n'
                    '    <td class="coldate">&nbsp;</td>\n'
                    '   </tr>\n' % (http.quote(item), escape(item)))
        for item in listing:
            itempath = os.path.join(path, item)
            if os.path.isfile(itempath):
                ext = os.path.splitext(item)[1].lstrip('.')
                size = os.path.getsize(itempath)
                mtime = os.path.getmtime(itempath)
                body += (
                    '   <tr class="item %s">\n'
                    '    <td class="colname"><a href="%s">%s</a></td>\n'
                    '    <td class="colsize">'
                    '<script type="text/javascript">'
                    'document.write(new Number(%s).toLocaleString());'
                    '</script></td>\n'
                    '    <td class="coldate">'
                    '<script type="text/javascript">'
                    'document.write(new Date(%s * 1000).toLocaleString());'
                    '</script></td>\n'
                    '   </tr>\n' %
                    ('ext' + ext, http.quote(item), escape(item), size, mtime))
        body += (
            '  </table>\n'
            ' </body>\n'
            '</html>\n')
        start_response('200 OK', {
            'content-type': 'text/html; charset=UTF-8',
            'content-length': str(len(body))}.items())
        return [body]

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
            'serve_path': conf.get_path(name, 'serve_path').rstrip('/')}
        if not parsed_conf['serve_path']:
            raise Exception('[%s] serve_path must be set' % name)
        return parsed_conf
