"""A simple WSGI application that just echoes the request body.

This is a good starting point for other WSGI applications. See the
source for what's implemented and why.

Configuration Options::

    [wsgi_echo]
    call = brim.wsgi_echo.WSGIEcho
    # path = <path>
    #   The request path to match and serve; any other paths will be
    #   passed on to the next WSGI app in the chain. Default: /echo
    # max_echo = <bytes>
    #   The maximum bytes to echo; any additional bytes will be ignored.
    #   Default: 65536

Stats Variables (where *n.* is the name of the app in the config):

==============  ======  ================================================
Name            Type    Description
==============  ======  ================================================
n.requests      sum     The number of requests received.
start_time      worker  Timestamp when the app was started. If the app
                        had to be restarted, this timestamp will be
                        updated with the new start time. This item is
                        available with all apps and set by the
                        controlling :py:class:`brim.server.Subserver`.
==============  ======  ================================================
"""
"""Copyright and License.

Copyright 2012-2014 Gregory Holt

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


class WSGIEcho(object):
    """A simple WSGI application that just echoes the request body.

    This is a good starting point for other WSGI applications. See the
    source for what's implemented and why.

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
        """The URL path to serve."""
        self.max_echo = parsed_conf['max_echo']
        """The maximum request size to echo back."""

    def __call__(self, env, start_response):
        """Handles incoming requests.

        If the request path exactly matches the one configured for this
        app, the request body will be read and then sent back in the
        response. Otherwise, the request is passed on to the next app in
        the chain.

        :param env: The WSGI env as per the spec.
        :param start_response: The WSGI start_response as per the spec.
        :returns: Calls *start_response* and returns an iterable as per
            the WSGI spec.
        """
        if env['PATH_INFO'] != self.path:
            return self.next_app(env, start_response)
        env['brim.stats'].incr('%s.requests' % self.name)
        body = []
        length = 0
        while length < self.max_echo:
            try:
                chunk = env['wsgi.input'].read(self.max_echo - length)
            except Exception:
                chunk = ''
            if not chunk:
                break
            length += len(chunk)
            body.append(chunk)
        start_response('200 OK', [('Content-Length', str(length))])
        return body

    @classmethod
    def parse_conf(cls, name, conf):
        """Translates the overall server configuration.

        The conf is translated into an app-specific configuration dict
        suitable for passing as ``parsed_conf`` in the
        :py:class:`WSGIEcho` constructor.

        See the overall docs of :py:mod:`brim.wsgi_echo` for
        configuration options.

        :param name: The name of the app, indicates the app's section in
            the overall configuration for the server.
        :param conf: The :py:class:`brim.conf.Conf` instance
            representing the overall configuration of the server.
        :returns: A dict suitable for passing as ``parsed_conf`` in the
            :py:class:`WSGIEcho` constructor.
        """
        return {'path': conf.get(name, 'path', '/echo'),
                'max_echo': conf.get_int(name, 'max_echo', 65536)}

    @classmethod
    def stats_conf(cls, name, parsed_conf):
        """Returns a list of (stat_name, stat_type) pairs.

        These pairs specify the stat variables this app wants
        established in the ``stats`` instance passed to
        :py:meth:`__call__`.

        Stats are often retrieved by users and utilities through WSGI
        apps like :py:class:`brim.wsgi_stats.WSGIStats`.

        See the overall docs of :py:mod:`brim.wsgi_echo` for what
        stats are defined.

        The available stat_types are:

        ======  ========================================================
        worker  Indicates a worker only stat. No overall stat will be
                reported.
        sum     Indicates an overall stat should be reported that is a
                sum of the stat from all workers.
        min     Indicates an overall stat should be reported that is the
                smallest value of the stat from all workers.
        max     Indicates an overall stat should be reported that is the
                largest value of the stat from all workers.
        ======  ========================================================

        :param name: The name of the app, indicates the app's section in
            the overall configuration for the daemon server.
        :param parsed_conf: The result from :py:meth:`parse_conf`.
        :returns: A list of (stat_name, stat_type) pairs.
        """
        return [('%s.requests' % name, 'sum')]
