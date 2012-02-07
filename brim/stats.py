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

See :py:func:`Stats.parse_conf` for configuration options.
"""

from sys import maxint


class Stats(object):
    """
    A WSGI application that reports the brimd server stats as a
    JSON reponse. The stats contain basic things like the server
    start time and request counts.

    :param name: The name of the app, indicates the app's section in
                 the overall configuration for the WSGI server.
    :param parsed_conf: The conf result from :py:func:`parse_conf`.
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
        subserver = env['brim']
        body = {}
        daemon_stats = subserver.daemon_bucket_stats
        for daemon_id in xrange(daemon_stats.bucket_count):
            daemon_body = {}
            for stat_name in daemon_stats.names:
                v = daemon_stats.get(daemon_id, stat_name)
                daemon_body[stat_name] = v
            body['daemon_' + subserver.daemons[daemon_id][0]] = daemon_body
        wsgi_worker_stats = subserver.wsgi_worker_bucket_stats
        sums = dict((n, 0) for n, t in
                    subserver.wsgi_worker_stats_conf.iteritems() if t == 'sum')
        mins = dict((n, maxint) for n, t in
                    subserver.wsgi_worker_stats_conf.iteritems() if t == 'min')
        maxs = dict((n, 0) for n, t in
                    subserver.wsgi_worker_stats_conf.iteritems() if t == 'max')
        for wsgi_worker_id in xrange(wsgi_worker_stats.bucket_count):
            wsgi_worker_body = {}
            for stat_name in wsgi_worker_stats.names:
                v = wsgi_worker_stats.get(wsgi_worker_id, stat_name)
                wsgi_worker_body[stat_name] = v
                if stat_name in sums:
                    sums[stat_name] += v
                if stat_name in mins:
                    mins[stat_name] = min(mins[stat_name], v)
                if stat_name in maxs:
                    maxs[stat_name] = max(maxs[stat_name], v)
            body['worker_%s' % wsgi_worker_id] = wsgi_worker_body
        body.update(sums)
        body.update(mins)
        body.update(maxs)
        body['start_time'] = subserver.start_time
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
