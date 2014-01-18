"""Tests for brim.udp_echo."""
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

from brim import udp_echo
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
        self.sendto_calls = []

    def sendto(self, *args, **kwargs):
        self.sendto_calls.append((args, kwargs))


class TestUDPEcho(TestCase):

    def test_call(self):
        subserver = FakeSubserver()
        stats = FakeStats()
        sock = FakeSocket(['1234'])
        ip = '1.2.3.4'
        port = 80
        datagram = '1234'
        udp_echo.UDPEcho('test', {})(subserver, stats, sock, datagram, ip,
                                     port)
        self.assertEqual(
            subserver.logger.notice_calls,
            [(('served request of 4 bytes from %s:%d' % (ip, port),), {})])
        self.assertEqual(stats.stats, {'byte_count': len(datagram)})
        self.assertEqual(sock.sendto_calls, [((datagram, (ip, port)), {})])

    def test_parse_conf(self):
        c = udp_echo.UDPEcho.parse_conf('test', Conf({}))
        self.assertEqual(c, {})

    def test_stats_conf(self):
        self.assertEqual(
            udp_echo.UDPEcho.stats_conf('test', {}), [('byte_count', 'sum')])


if __name__ == '__main__':
    main()
