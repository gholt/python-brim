# Copyright 2012 Gregory Holt
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Contains a simple WSGI application that just echoes the request body
back in the response. This is a good starting point for other WSGI
applications. See the source for what's implemented and why.

See :py:func:`WSGIEcho.parse_conf` for configuration options.
"""


class WSGIEcho(object):
    """
    A simple WSGI application that just echoes the request body back
    in the response. This is a good starting point for other WSGI
    applications. See the source for what's implemented and why.

    :param name: The name of the app, indicates the app's section in
                 the overall configuration for the server.
    :param parsed_conf: The conf result from :py:func:`parse_conf`.
    :param next_app: The next WSGI app in the chain.
    """

    def __init__(self, name, parsed_conf, next_app):
        # Copy all items from the parsed_conf to actual instance attributes.
        for k, v in parsed_conf.iteritems():
            setattr(self, k, v)
        self.name = name
        self.next_app = next_app

    def __call__(self, env, start_response):
        """
        If the request path matches the one configured for this app,
        the request body will be read and then sent back in the
        response. Otherwise, the request is passed on to the next app
        in the chain.

        :param env: The WSGI env as per the spec.
        :param start_response: The WSGI start_response as per the
                               spec.
        :returns: Calls start_response and returns an iterable as
                  per the WSGI spec.
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
        """
        Translates the overall server configuration into an
        app-specific configuration dict suitable for passing as
        ``parsed_conf`` in the WSGIEcho constructor.

        Sample Configuration File::

            [wsgi_echo]
            call = brim.wsgi_echo.WSGIEcho
            # path = <path>
            #   The request path to match and serve; any other paths
            #   will be passed on to the next WSGI app in the chain.
            #   Default: /echo
            # max_echo = <bytes>
            #   The maximum bytes to echo; any additional bytes will
            #   be ignored. Default: 65536

        :param name: The name of the app, indicates the app's section
                     in the overall configuration for the server.
        :param conf: The brim.conf.Conf instance representing the
                     overall configuration of the server.
        :returns: A dict suitable for passing as ``parsed_conf`` in
                  the WSGIEcho constructor.
        """
        return {'path': conf.get(name, 'path', '/echo'),
                'max_echo': conf.get_int(name, 'max_echo', 65536)}

    @classmethod
    def stats_conf(cls, name, parsed_conf):
        """
        Returns a list of (stat_name, stat_type) pairs that specifies
        the stat variables this app wants established. stat_name is
        the str name of the stat and stat_type is one of the
        following:

        worker

            Indicates a worker only stat. No overall stat will be
            reported.

        sum

            Indicates an overall stat should be reported that is a
            sum of the stat from all workers.

        min

            Indicates an overall stat should be reported that is the
            smallest value of the stat from all workers.

        max

            Indicates an overall stat should be reported that is the
            largest value of the stat from all workers.

        Within the app itself, these stats can be accessed through
        the object at ``env['brim.stats']``. This object will
        support the following methods:

        get(<name>)

            Return the int value of the stat <name>.

        set(<name>, value)

            Sets the value of the stat <name>. The value will be
            treated as an unsigned integer.


        incr(<name>)

            Increments the value of the stat <name> by 1.

        Retreiving stats can be accomplished through WSGI apps like
        brim.stats.Stats.

        :param name: The name of the app, indicates the app's section
                     in the overall configuration for the server.
        :param parsed_conf: The conf result from
                            :py:func:`parse_conf`.
        :returns: A list of (stat_name, stat_type) pairs.
        """
        return [('%s.requests' % name, 'sum')]
