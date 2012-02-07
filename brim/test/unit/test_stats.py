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

from json import dumps, loads
from StringIO import StringIO
from time import time
from unittest import main, TestCase

from brim import stats
from brim.conf import Conf


class FakeStats(object):

    def __init__(self):
        self.bucket_count = 2
        self.names = ['one', 'two', 'three', 'four']
        self.stats = [{}, {}]

    def get(self, bucket_id, name):
        return self.stats[bucket_id].get(name, 0)

    def set(self, bucket_id, name, value):
        self.stats[bucket_id][name] = value

    def incr(self, bucket_id, name):
        self.stats[bucket_id][name] = self.stats[bucket_id].get(name, 0) + 1


class FakeServer(object):

    def __init__(self):
        self.daemons = [('daemon1',), ('daemon2',)]
        self.daemon_bucket_stats = FakeStats()
        self.wsgi_worker_stats_conf = {'one': 'worker', 'two': 'sum',
                                       'three': 'min', 'four': 'max'}
        self.wsgi_worker_bucket_stats = FakeStats()
        self.start_time = 1234


class TestStats(TestCase):

    def setUp(self):
        self.next_app_calls = []
        self.start_response_calls = []

        def _next_app(env, start_response):
            self.next_app_calls.append((env, start_response))
            start_response('204 No Content', ('Content-Length', '0'))
            return []

        def _start_response(*args):
            self.start_response_calls.append(args)

        self.next_app = _next_app
        self.start_response = _start_response
        self.env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/testpath',
                    'brim': FakeServer(),
                    'wsgi.input': StringIO('testbody'),
                    'brim.json_dumps': dumps,
                    'brim.json_loads': loads}
        self.parsed_conf = {'path': '/testpath'}

    def test_init_attrs(self):
        e = stats.Stats('test', {}, None)
        self.assertEquals(getattr(e, 'testattr', None), None)
        e = stats.Stats('test', {'testattr': 1}, None)
        self.assertEquals(getattr(e, 'testattr', None), 1)

    def test_call_ignores_non_path(self):
        self.env['PATH_INFO'] = '/'
        stats.Stats('test', self.parsed_conf,
                  self.next_app)(self.env, self.start_response)
        self.assertEquals(self.next_app_calls,
                          [(self.env, self.start_response)])
        self.assertEquals(self.start_response_calls,
                          [('204 No Content', ('Content-Length', '0'))])

    def test_call_not_implemented(self):
        self.env['REQUEST_METHOD'] = 'PUT'
        body = ''.join(stats.Stats('test', self.parsed_conf,
                                 self.next_app)(self.env, self.start_response))
        self.assertEquals(self.start_response_calls,
                          [('501 Not Implemented',
                            [('Content-Length', '0')])])
        self.assertEquals(body, '')

    def test_call_stats_zeroed(self):
        body = ''.join(stats.Stats('test', self.parsed_conf,
                                 self.next_app)(self.env, self.start_response))
        self.assertEquals(self.start_response_calls,
                          [('200 OK', [('Content-Length', '294'),
                                       ('Content-Type', 'application/json')])])
        self.assertEquals(loads(body),
            {"start_time": 1234, "two": 0, "three": 0, "four": 0,
             "daemon_daemon1": {"one": 0, "two": 0, "three": 0, "four": 0},
             "daemon_daemon2": {"one": 0, "two": 0, "three": 0, "four": 0},
             "worker_0": {"one": 0, "two": 0, "three": 0, "four": 0},
             "worker_1": {"one": 0, "two": 0, "three": 0, "four": 0}})

    def test_call_stats_zeroed_head(self):
        self.env['REQUEST_METHOD'] = 'HEAD'
        body = ''.join(stats.Stats('test', self.parsed_conf,
                                 self.next_app)(self.env, self.start_response))
        self.assertEquals(self.start_response_calls,
                          [('200 OK', [('Content-Length', '294'),
                                       ('Content-Type', 'application/json')])])
        self.assertEquals(body, '')

    def test_call_stats(self):
        self.env['brim'].daemon_bucket_stats.set(0, 'one', 101)
        self.env['brim'].daemon_bucket_stats.set(0, 'two', 102)
        self.env['brim'].daemon_bucket_stats.set(0, 'three', 103)
        self.env['brim'].daemon_bucket_stats.set(0, 'four', 104)
        self.env['brim'].daemon_bucket_stats.set(1, 'one', 201)
        self.env['brim'].daemon_bucket_stats.set(1, 'two', 202)
        self.env['brim'].daemon_bucket_stats.set(1, 'three', 203)
        self.env['brim'].daemon_bucket_stats.set(1, 'four', 204)
        self.env['brim'].wsgi_worker_bucket_stats.set(0, 'one', 111)
        self.env['brim'].wsgi_worker_bucket_stats.set(0, 'two', 112)
        self.env['brim'].wsgi_worker_bucket_stats.set(0, 'three', 113)
        self.env['brim'].wsgi_worker_bucket_stats.set(0, 'four', 114)
        self.env['brim'].wsgi_worker_bucket_stats.set(1, 'one', 211)
        self.env['brim'].wsgi_worker_bucket_stats.set(1, 'two', 212)
        self.env['brim'].wsgi_worker_bucket_stats.set(1, 'three', 213)
        self.env['brim'].wsgi_worker_bucket_stats.set(1, 'four', 214)
        body = ''.join(stats.Stats('test', self.parsed_conf,
                                 self.next_app)(self.env, self.start_response))
        self.assertEquals(self.start_response_calls,
                          [('200 OK', [('Content-Length', '332'),
                                       ('Content-Type', 'application/json')])])
        self.assertEquals(loads(body),
            {"start_time": 1234, "two": 112 + 212, "three": 113, "four": 214,
             "daemon_daemon1": {"one": 101, "two": 102, "three": 103,
                                "four": 104},
             "daemon_daemon2": {"one": 201, "two": 202, "three": 203,
                                "four": 204},
             "worker_0": {"one": 111, "two": 112, "three": 113, "four": 114},
             "worker_1": {"one": 211, "two": 212, "three": 213, "four": 214}})

    def test_parse_conf(self):
        c = stats.Stats.parse_conf('test', Conf({}))
        self.assertEquals(c, {'path': '/stats'})
        c = stats.Stats.parse_conf('test', Conf({'test': {'path': '/blah'}}))
        self.assertEquals(c, {'path': '/blah'})
        c = stats.Stats.parse_conf('test', Conf({'test2': {'path': '/blah'}}))
        self.assertEquals(c, {'path': '/stats'})


if __name__ == '__main__':
    main()
