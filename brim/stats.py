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
Reports the brimd server stats as a JSON reponse. The stats
contain basic things like the server start time and request counts.

See Stats.parse_conf for configuration options.
"""

from sys import maxint
from brim.http import QueryParser


class Stats(object):
    """
    A WSGI application that reports the brimd server stats as a
    JSON reponse. The stats contain basic things like the server
    start time and request counts.

    :param name: The name of the app, indicates the app's section in
                 the overall configuration for the WSGI server.
    :param parsed_conf: The conf result from parse_conf.
    :param next_app: The next WSGI app in the chain.
    """

    def __init__(self, name, parsed_conf, next_app):
        # Copy all items from the parsed_conf to actual instance attributes.
        for k, v in parsed_conf.iteritems():
            setattr(self, k, v)
        self.next_app = next_app

    def __call__(self, env, start_response):
        """
        If the request path matches the one configured for this app,
        a JSON response will be sent containing the brimd server
        stats. Otherwise, the request is passed on to the next app in
        the chain.

        :param env: The WSGI env as per the spec.
        :param start_response: The WSGI start_response as per the spec.
        :returns: Calls start_response and returns an iteratable as
                  per the WSGI spec.
        """
        if env['PATH_INFO'] != self.path:
            return self.next_app(env, start_response)
        if env['REQUEST_METHOD'] not in ('GET', 'HEAD'):
            start_response('501 Not Implemented', [('Content-Length', '0')])
            return []
        server = env['brim'].server
        body = {}
        for index, subserver in enumerate(server.subservers):
            body[subserver.name] = {}
            stats = server.bucket_stats[index]
            if stats.bucket_count == 1:
                for name, typ in stats.stats_conf.iteritems():
                    body[subserver.name][name] = stats.get(0, name)
            else:
                for name, typ in stats.stats_conf.iteritems():
                    if typ == 'sum':
                        body[subserver.name][name] = sum(
                            stats.get(i, name)
                            for i in xrange(stats.bucket_count))
                    elif typ == 'min':
                        body[subserver.name][name] = min(
                            stats.get(i, name)
                            for i in xrange(stats.bucket_count))
                    elif typ == 'max':
                        body[subserver.name][name] = max(
                            stats.get(i, name)
                            for i in xrange(stats.bucket_count))
                    for i in xrange(stats.bucket_count):
                        body[subserver.name].setdefault(
                            stats.bucket_names[i],
                            {})[name] = stats.get(i, name)
        body['start_time'] = server.start_time
        qp = QueryParser(env['QUERY_STRING'])
        callback = qp.get('jsonp', default=qp.get('callback', default=False))
        if callback:
            body = '%s(%s)' % (callback, env['brim.json_dumps'](body))
            start_response('200 OK', [('Content-Length', str(len(body))),
                                      ('Content-Type',
                                       'application/javascript')])
        else:
            body = env['brim.json_dumps'](body) + '\n'
            start_response('200 OK', [('Content-Length', str(len(body))),
                                      ('Content-Type', 'application/json')])
        if env['REQUEST_METHOD'] == 'HEAD':
            return []
        return [body]

    @classmethod
    def parse_conf(cls, name, conf):
        """
        Translates the overall WSGI server configuration into an
        app-specific configuration dict suitable for passing as
        ``parsed_conf`` in the Stats constructor.

        Sample Configuration File::

            [stats]
            call = brim.stats.Stats
            # path = <path>
            #   The request path to match and serve; any other paths
            #   will be passed on to the next WSGI app in the chain.
            #   This can serve as a basic restriction to accessing
            #   the stats by setting it to a hard to guess value.
            #   Default: /stats

        :param name: The name of the app, indicates the app's section
                     in the overall configuration for the WSGI
                     server.
        :param conf: The brim.conf.Conf instance representing the
                     overall configuration of the WSGI server.
        :returns: A dict suitable for passing as ``parsed_conf`` in
                  the Stats constructor.
        """
        return {'path': conf.get(name, 'path', '/stats')}
