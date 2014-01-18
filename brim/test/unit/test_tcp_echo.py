"""Tests for brim.tcp_echo."""
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
from unittest import main, TestCase

from brim import tcp_echo
from brim.conf import Conf


class FakeLogger(object):

    def __init__(self):
        self.notice_calls = []

    def notice(self, *args, **kwargs):
        self.notice_calls.append((args, kwargs))


class FakeSubserver(object):

    def __init__(self):
        self.logger = FakeLogger()


class FakeStats(object):

    def __init__(self):
        self.stats = {}

    def get(self, name):
        return self.stats.get(name, 0)

    def set(self, name, value):
        self.stats[name] = value

    def incr(self, name):
        self.stats[name] = self.stats.get(name, 0) + 1


class FakeSocket(object):

    def __init__(self, content=None, chunk_write=None):
        self.content = iter(content or [])
        self.chunk_write = chunk_write
        self.recv_calls = []
        self.send_calls = []
        self.close_calls = []

    def recv(self, *args, **kwargs):
        self.recv_calls.append((args, kwargs))
        try:
            return self.content.next()
        except Exception:
            return ''

    def send(self, data):
        if self.chunk_write:
            data = data[:self.chunk_write]
        self.send_calls.append(data)
        return len(data)

    def close(self, *args, **kwargs):
        self.close_calls.append((args, kwargs))


class TestTCPEcho(TestCase):

    def setUp(self):
        self.parsed_conf = {'chunk_read': 1234}

    def test_call(self):
        subserver = FakeSubserver()
        stats = FakeStats()
        sock = FakeSocket(['1234'])
        ip = '1.2.3.4'
        port = 80
        tcp_echo.TCPEcho('test', self.parsed_conf)(
            subserver, stats, sock, ip, port)
        self.assertEqual(
            subserver.logger.notice_calls,
            [(('served request from %s:%s' % (ip, port),), {})])
        self.assertEqual(stats.stats, {'byte_count': 4})
        self.assertEqual(sock.recv_calls, [((1234,), {})] * 2)
        self.assertEqual(sock.send_calls, ['1234'])
        self.assertEqual(sock.close_calls, [((), {})])

    def test_call_chunked_reads(self):
        subserver = FakeSubserver()
        stats = FakeStats()
        sock = FakeSocket(['1234', '5678', '90'])
        ip = '1.2.3.4'
        port = 80
        tcp_echo.TCPEcho('test', self.parsed_conf)(
            subserver, stats, sock, ip, port)
        self.assertEqual(
            subserver.logger.notice_calls,
            [(('served request from %s:%s' % (ip, port),), {})])
        self.assertEqual(stats.stats, {'byte_count': 10})
        self.assertEqual(sock.recv_calls, [((1234,), {})] * 4)
        self.assertEqual(sock.send_calls, ['1234', '5678', '90'])
        self.assertEqual(sock.close_calls, [((), {})])

    def test_call_chunked_writes(self):
        subserver = FakeSubserver()
        stats = FakeStats()
        sock = FakeSocket(['12345'], chunk_write=2)
        ip = '1.2.3.4'
        port = 80
        tcp_echo.TCPEcho('test', self.parsed_conf)(
            subserver, stats, sock, ip, port)
        self.assertEqual(
            subserver.logger.notice_calls,
            [(('served request from %s:%s' % (ip, port),), {})])
        self.assertEqual(stats.stats, {'byte_count': 5})
        self.assertEqual(sock.recv_calls, [((1234,), {})] * 2)
        self.assertEqual(sock.send_calls, ['12', '34', '5'])
        self.assertEqual(sock.close_calls, [((), {})])

    def test_parse_conf(self):
        c = tcp_echo.TCPEcho.parse_conf('test', Conf({}))
        self.assertEqual(c, {'chunk_read': 65536})
        c = tcp_echo.TCPEcho.parse_conf(
            'test', Conf({'test': {'chunk_read': '1234'}}))
        self.assertEqual(c, {'chunk_read': 1234})
        exc = None
        try:
            c = tcp_echo.TCPEcho.parse_conf(
                'test', Conf({'test': {'chunk_read': 'abc'}}))
        except SystemExit as err:
            exc = err
        self.assertEqual(
            str(exc),
            "Configuration value [test] chunk_read of 'abc' cannot be "
            "converted to int.")

    def test_stats_conf(self):
        self.assertEqual(tcp_echo.TCPEcho.stats_conf(
            'test', self.parsed_conf), [('byte_count', 'sum')])


if __name__ == '__main__':
    main()
