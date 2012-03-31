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

from contextlib import contextmanager
from pickle import dumps as pickle_dumps, loads as pickle_loads
from json import dumps as json_dumps, loads as json_loads
from StringIO import StringIO
from socket import error as socket_error
from sys import exc_info
from time import mktime, strptime, time
from unittest import main, TestCase
from uuid import uuid4

from brim import server, version
from brim.conf import Conf
from brim.service import get_listening_tcp_socket


class TestLogQuote(TestCase):

    def test_log_quote(self):
        self.assertEquals(
            server._log_quote(''.join(chr(c) for c in xrange(256))),
            '%00%01%02%03%04%05%06%07%08%09%0A%0B%0C%0D%0E%0F'
            '%10%11%12%13%14%15%16%17%18%19%1A%1B%1C%1D%1E%1F'
            '%20!"#$%25&\'()*+,-./0123456789:;<=>?@'
            'ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`'
            'abcdefghijklmnopqrstuvwxyz{|}~%7F'
            '%80%81%82%83%84%85%86%87%88%89%8A%8B%8C%8D%8E%8F'
            '%90%91%92%93%94%95%96%97%98%99%9A%9B%9C%9D%9E%9F'
            '%A0%A1%A2%A3%A4%A5%A6%A7%A8%A9%AA%AB%AC%AD%AE%AF'
            '%B0%B1%B2%B3%B4%B5%B6%B7%B8%B9%BA%BB%BC%BD%BE%BF'
            '%C0%C1%C2%C3%C4%C5%C6%C7%C8%C9%CA%CB%CC%CD%CE%CF'
            '%D0%D1%D2%D3%D4%D5%D6%D7%D8%D9%DA%DB%DC%DD%DE%DF'
            '%E0%E1%E2%E3%E4%E5%E6%E7%E8%E9%EA%EB%EC%ED%EE%EF'
            '%F0%F1%F2%F3%F4%F5%F6%F7%F8%F9%FA%FB%FC%FD%FE%FF')


class TestStats(TestCase):

    def test_bucket_stats(self):
        bs = server._BucketStats(['testbucket'], {'test': 'worker'})
        self.assertEquals(bs.get(0, 'test'), 0)
        bs.set(0, 'test', 123)
        self.assertEquals(bs.get(0, 'test'), 123)
        bs.incr(0, 'test')
        self.assertEquals(bs.get(0, 'test'), 124)

        self.assertEquals(bs.get(0, 'test2'), 0)
        bs.set(0, 'test2', 123)
        self.assertEquals(bs.get(0, 'test2'), 0)
        bs.incr(0, 'test2')
        self.assertEquals(bs.get(0, 'test2'), 0)

        self.assertRaises(IndexError, bs.get, 1, 'test')
        self.assertRaises(IndexError, bs.set, 1, 'test', 123)
        self.assertRaises(IndexError, bs.incr, 1, 'test')

    def test_null_bucket_stats(self):
        bs = server._BucketStats([], {})
        self.assertEquals(bs.get(0, 'test'), 0)
        bs.set(0, 'test', 123)
        self.assertEquals(bs.get(0, 'test'), 0)
        bs.incr(0, 'test')
        self.assertEquals(bs.get(0, 'test'), 0)

        bs = server._BucketStats([], {'test': 'worker'})
        self.assertEquals(bs.get(0, 'test'), 0)
        bs.set(0, 'test', 123)
        self.assertEquals(bs.get(0, 'test'), 0)
        bs.incr(0, 'test')
        self.assertEquals(bs.get(0, 'test'), 0)

    def test_stats(self):
        bs = server._BucketStats(['testbucket'], ['test'])
        s = server._Stats(bs, 0)
        self.assertEquals(s.get('test'), 0)
        s.set('test', 123)
        self.assertEquals(s.get('test'), 123)
        s.incr('test')
        self.assertEquals(s.get('test'), 124)

        self.assertEquals(s.get('test2'), 0)
        s.set('test2', 123)
        self.assertEquals(s.get('test2'), 0)
        s.incr('test2')
        self.assertEquals(s.get('test2'), 0)

        s = server._Stats(bs, 1)
        self.assertRaises(IndexError, s.get, 'test')
        self.assertRaises(IndexError, s.set, 'test', 123)
        self.assertRaises(IndexError, s.incr, 'test')


class TestEventletWSGINullLogger(TestCase):

    def test_write(self):
        server._EventletWSGINullLogger().write('abc', 'def', 'ghi')


class TestWsgiInput(TestCase):

    def setUp(self):
        self.sio = StringIO('1234567890')
        self.env = {'wsgi.input': self.sio, 'brim._bytes_in': 0}
        self.inp = server._WsgiInput(self.env, 3)

    def test_sets_as_self(self):
        self.assertEquals(self.env['wsgi.input'], self.inp)

    def test_close(self):
        self.inp.close()
        exc = None
        try:
            self.inp.read()
        except Exception, err:
            exc = err
        self.assertEquals(str(err), 'I/O operation on closed file')

    def test_flush(self):
        self.inp.flush()

    def test_fileno(self):
        exc = None
        try:
            self.inp.fileno()
        except Exception, err:
            exc = err
        self.assertEquals(str(err),
                          "StringIO instance has no attribute 'fileno'")

    def test_iterator(self):
        self.assertEquals([c for c in self.inp], ['123', '456', '789', '0'])
        self.assertEquals(self.env['brim._bytes_in'], 10)

    def test_read(self):
        self.assertEquals(self.inp.read(4), '1234')
        self.assertEquals(self.env['brim._bytes_in'], 4)
        self.assertEquals(self.inp.read(), '567890')
        self.assertEquals(self.env['brim._bytes_in'], 10)

    def test_readline(self):
        self.sio = StringIO('1234567890\nabcdefghij\nklmnopqrst')
        self.env = {'wsgi.input': self.sio, 'brim._bytes_in': 0}
        self.inp = server._WsgiInput(self.env, 3)
        self.assertEquals(self.inp.readline(), '1234567890\n')
        self.assertEquals(self.env['brim._bytes_in'], 11)
        self.assertEquals(self.inp.readline(2), 'ab')
        self.assertEquals(self.env['brim._bytes_in'], 13)
        self.assertEquals(self.inp.readline(20), 'cdefghij\n')
        self.assertEquals(self.env['brim._bytes_in'], 22)
        self.assertEquals(self.inp.readline(), 'klmnopqrst')
        self.assertEquals(self.env['brim._bytes_in'], 32)

    def test_readlines(self):
        self.sio = StringIO('1234567890\nabcdefghij\nklmnopqrst\nuvwxyz')
        self.env = {'wsgi.input': self.sio, 'brim._bytes_in': 0}
        self.inp = server._WsgiInput(self.env, 3)
        self.assertEquals(self.inp.readlines(15),
                          ['1234567890\n', 'abcdefghij\n'])
        self.assertEquals(self.env['brim._bytes_in'], 22)
        self.assertEquals(self.inp.readlines(), ['klmnopqrst\n', 'uvwxyz'])
        self.assertEquals(self.env['brim._bytes_in'], 39)


class TestWsgiOutput(TestCase):

    def test_wsgi_output(self):
        env = {'brim._bytes_out': 0}
        o = server._WsgiOutput(['123', '456', '78', '90'], env)
        self.assertEquals(o.next(), '123')
        self.assertEquals(env['brim._bytes_out'], 3)
        self.assertEquals([c for c in o], ['456', '78', '90'])


class TestSendPidSig(TestCase):

    def setUp(self):
        self.orig_kill = server.kill
        self.orig_time = server.time
        self.orig_sleep = server.sleep
        self.orig_unlink = server.unlink
        self.open_calls = []
        self.open_retval = [StringIO('12345')]
        self.kill_calls = []
        self.time_calls = []
        self.sleep_calls = []
        self.unlink_calls = []

        @contextmanager
        def _open(*args):
            self.open_calls.append(args)
            yield self.open_retval[0]

        def _kill(*args):
            self.kill_calls.append(args)

        def _time(*args):
            self.time_calls.append(args)
            return len(self.time_calls)

        def _sleep(*args):
            self.sleep_calls.append(args)

        def _unlink(*args):
            self.unlink_calls.append(args)

        server.open = _open
        server.kill = _kill
        server.time = _time
        server.sleep = _sleep
        server.unlink = _unlink

    def tearDown(self):
        del server.open
        server.kill = self.orig_kill
        server.time = self.orig_time
        server.sleep = self.orig_sleep
        server.unlink = self.orig_unlink

    def test_open_not_found(self):

        @contextmanager
        def _open(*args):
            exc = IOError('testing')
            exc.errno = server.ENOENT
            raise exc

        server.open = _open
        self.assertEquals(server._send_pid_sig('some.pid', 0), (False, 0))

    def test_open_exception(self):

        @contextmanager
        def _open(*args):
            raise IOError('testing')

        server.open = _open
        exc = None
        try:
            server._send_pid_sig('some.pid', 0)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), 'testing')

    def test_pid_file_no_int(self):
        self.open_retval[0] = StringIO('')
        self.assertEquals(server._send_pid_sig('some.pid', 0), (False, 0))

    def test_kill_inactive_pid(self):

        def _kill(*args):
            exc = OSError('testing')
            exc.errno = server.ESRCH
            raise exc

        server.kill = _kill
        self.open_retval[0] = StringIO('12345')
        self.assertEquals(server._send_pid_sig('some.pid', 0), (False, 12345))

    def test_kill_exception(self):

        def _kill(*args):
            raise OSError('testing')

        server.kill = _kill
        self.open_retval[0] = StringIO('12345')
        exc = None
        try:
            server._send_pid_sig('some.pid', 0)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), 'testing')

    def test_kill_worked(self):
        self.open_retval[0] = StringIO('12345')
        self.assertEquals(server._send_pid_sig('some.pid', 0), (True, 12345))

    def test_kill_expect_exit_timeout(self):
        self.open_retval[0] = StringIO('12345')
        exc = None
        try:
            server._send_pid_sig('some.pid', 0, expect_exit=True)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            '12345 did not exit after %s seconds.' % server.PID_WAIT_TIME)
        self.assertEquals(self.time_calls, [()] * (server.PID_WAIT_TIME + 1))
        self.assertEquals(self.sleep_calls,
                          [(1,)] * (server.PID_WAIT_TIME - 1))
        self.assertEquals(self.unlink_calls, [])

    def test_kill_expect_exit_worked(self):
        kill_calls = []

        def _kill(*args):
            kill_calls.append(args)
            if len(kill_calls) > 3:
                exc = OSError()
                exc.errno = server.ESRCH
                raise exc

        server.kill = _kill
        self.open_retval[0] = StringIO('12345')
        server._send_pid_sig('some.pid', 0, expect_exit=True)
        self.assertEquals(self.time_calls, [()] * 3)
        self.assertEquals(self.sleep_calls, [(1,)] * 2)
        self.assertEquals(self.unlink_calls, [('some.pid',)])

    def test_kill_expect_exit_kill_exception(self):
        kill_calls = []

        def _kill(*args):
            kill_calls.append(args)
            if len(kill_calls) > 3:
                raise OSError('testing')

        server.kill = _kill
        self.open_retval[0] = StringIO('12345')
        exc = None
        try:
            server._send_pid_sig('some.pid', 0, expect_exit=True)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), 'testing')
        self.assertEquals(self.time_calls, [()] * 3)
        self.assertEquals(self.sleep_calls, [(1,)] * 2)
        self.assertEquals(self.unlink_calls, [])

    def test_kill_expect_exit_unlink_not_found(self):
        kill_calls = []
        unlink_calls = []

        def _kill(*args):
            kill_calls.append(args)
            if len(kill_calls) > 1:
                exc = OSError()
                exc.errno = server.ESRCH
                raise exc

        def _unlink(*args):
            unlink_calls.append(args)
            exc = OSError()
            exc.errno = server.ENOENT
            raise exc

        server.kill = _kill
        server.unlink = _unlink
        self.open_retval[0] = StringIO('12345')
        self.assertEquals(server._send_pid_sig('some.pid', 0,
                                               expect_exit=True),
                          (True, 12345))
        self.assertEquals(unlink_calls, [('some.pid',)])

    def test_kill_expect_exit_unlink_exception(self):
        kill_calls = []

        def _kill(*args):
            kill_calls.append(args)
            if len(kill_calls) > 1:
                exc = OSError()
                exc.errno = server.ESRCH
                raise exc

        def _unlink(*args):
            raise OSError('testing')

        server.kill = _kill
        server.unlink = _unlink
        self.open_retval[0] = StringIO('12345')
        exc = None
        try:
            server._send_pid_sig('some.pid', 0, expect_exit=True)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), 'testing')


class FakeServer(object):

    def __init__(self, no_daemon=False, output=False):
        self.no_daemon = no_daemon
        self.output = output


class TestSubserver(TestCase):

    _class = server.Subserver

    def _get_default_confd(self):
        return {}

    def test_init(self):
        s = FakeServer()
        ss = self._class(s, 'test')
        self.assertEquals(ss.server, s)
        self.assertEquals(ss.name, 'test')
        self.assertEquals(ss.worker_count, 1)
        self.assertEquals(ss.worker_names, ['0'])
        self.assertEquals(ss.stats_conf.get('start_time'), 'worker')
        return ss

    def test_parse_conf_defaults(self):
        ss = self._class(FakeServer(), 'test')
        ss._parse_conf(Conf(self._get_default_confd()))
        self.assertEquals(ss.log_name, 'brimtest')
        self.assertEquals(ss.log_level, 'INFO')
        self.assertEquals(ss.log_facility, 'LOG_LOCAL0')
        self.assertEquals(ss.json_dumps, json_dumps)
        self.assertEquals(ss.json_loads, json_loads)
        return ss

    def test_parse_conf_log_name(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['log_name'] = 'name'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.log_name, 'nametest')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['log_name'] = 'name'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.log_name, 'name')

    def test_parse_conf_log_level(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['log_level'] = 'DEBUG'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.log_level, 'DEBUG')

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['log_level'] = 'invalid'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(err), "Invalid [test] log_level 'INVALID'.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['log_level'] = 'DEBUG'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.log_level, 'DEBUG')

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['log_level'] = 'invalid'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(err), "Invalid [test] log_level 'INVALID'.")

    def test_parse_conf_log_facility(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['log_facility'] = 'LOG_LOCAL1'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.log_facility, 'LOG_LOCAL1')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['log_facility'] = 'LOCAL2'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.log_facility, 'LOG_LOCAL2')

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['log_facility'] = 'invalid'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(err),
                          "Invalid [test] log_facility 'LOG_INVALID'.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['log_facility'] = 'LOG_LOCAL1'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.log_facility, 'LOG_LOCAL1')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['log_facility'] = 'LOCAL2'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.log_facility, 'LOG_LOCAL2')

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['log_facility'] = 'invalid'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(err),
                          "Invalid [test] log_facility 'LOG_INVALID'.")

    def test_parse_conf_json_dumps(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['json_dumps'] = 'pickle.dumps'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.json_dumps, pickle_dumps)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['json_dumps'] = 'abc'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid [test] json_dumps value 'abc'.")

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['json_dumps'] = 'pickle.blah'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            "Could not load function 'pickle.blah' for [test] json_dumps.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['json_dumps'] = 'pickle.dumps'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.json_dumps, pickle_dumps)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['json_dumps'] = 'abc'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid [test] json_dumps value 'abc'.")

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['json_dumps'] = 'pickle.blah'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            "Could not load function 'pickle.blah' for [test] json_dumps.")

    def test_parse_conf_json_loads(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['json_loads'] = 'pickle.loads'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.json_loads, pickle_loads)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['json_loads'] = 'abc'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid [test] json_loads value 'abc'.")

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['json_loads'] = 'pickle.blah'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            "Could not load function 'pickle.blah' for [test] json_loads.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['json_loads'] = 'pickle.loads'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.json_loads, pickle_loads)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['json_loads'] = 'abc'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid [test] json_loads value 'abc'.")

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['json_loads'] = 'pickle.blah'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            "Could not load function 'pickle.blah' for [test] json_loads.")

    def test_privileged_start(self):
        # Just makes sure the method exists [it is just "pass" by default].
        self._class(FakeServer(), 'test')._privileged_start()

    def test_start(self, output=False, no_daemon=False, func_before_start=None,
                   bucket_stats=None, confd=None):
        if bucket_stats is None:
            bucket_stats = \
                server._BucketStats(['testbucket'], {'test': 'worker'})
        ss = self._class(FakeServer(output=output, no_daemon=no_daemon),
                         'test')
        confd = confd if confd else self._get_default_confd()
        confd.setdefault('brim', {})['port'] = '0'
        ss._parse_conf(Conf(confd))
        ss._privileged_start()
        if func_before_start:
            func_before_start(ss)
        ss._start(bucket_stats)
        self.assertEquals(ss.bucket_stats, bucket_stats)
        return ss


class TestIPSubserver(TestSubserver):

    _class = server.IPSubserver
    _override_workers = None

    def test_parse_conf_defaults(self):
        ss = TestSubserver.test_parse_conf_defaults(self)
        self.assertEquals(ss.ip, '*')
        self.assertEquals(ss.port, 80)
        self.assertEquals(ss.certfile, None)
        self.assertEquals(ss.keyfile, None)
        self.assertEquals(ss.client_timeout, 60)
        self.assertEquals(ss.concurrent_per_worker, 1024)
        self.assertEquals(ss.backlog, 4096)
        self.assertEquals(ss.listen_retry, 30)
        self.assertEquals(ss.eventlet_hub, None)

        ss.server.no_daemon = True
        ss = self._class(ss.server, 'test')
        ss._parse_conf(Conf(self._get_default_confd()))
        if self._override_workers is None:
            self.assertEquals(ss.worker_count, 0)
            self.assertEquals(ss.worker_names, ['0'])
        else:
            self.assertEquals(ss.worker_count, self._override_workers)
            self.assertEquals(ss.worker_names,
                              [str(x) for x in xrange(self._override_workers)])
        return ss

    def test_parse_conf_ip(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['ip'] = '1.2.3.4'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.ip, '1.2.3.4')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['ip'] = '1.2.3.4'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.ip, '1.2.3.4')

    def test_parse_conf_port(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['port'] = '1234'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.port, 1234)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['port'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] port of "
                                    "'abc' cannot be converted to int.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['port'] = '1234'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.port, 1234)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['port'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [test] port of "
                                    "'abc' cannot be converted to int.")

    def test_parse_conf_certfile(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['certfile'] = 'file'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.certfile, 'file')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['certfile'] = 'file'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.certfile, 'file')

    def test_parse_conf_keyfile(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['keyfile'] = 'file'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.keyfile, 'file')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['keyfile'] = 'file'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.keyfile, 'file')

    def test_parse_conf_client_timeout(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['client_timeout'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.client_timeout, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['client_timeout'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] "
            "client_timeout of 'abc' cannot be converted to int.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['client_timeout'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.client_timeout, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['client_timeout'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [test] "
            "client_timeout of 'abc' cannot be converted to int.")

    def test_parse_conf_concurrent_per_worker(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['concurrent_per_worker'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.concurrent_per_worker, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['concurrent_per_worker'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] "
            "concurrent_per_worker of 'abc' cannot be converted to int.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['concurrent_per_worker'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.concurrent_per_worker, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['concurrent_per_worker'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [test] "
            "concurrent_per_worker of 'abc' cannot be converted to int.")

    def test_parse_conf_backlog(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['backlog'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.backlog, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['backlog'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] backlog "
                                    "of 'abc' cannot be converted to int.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['backlog'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.backlog, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['backlog'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [test] backlog "
                                    "of 'abc' cannot be converted to int.")

    def test_parse_conf_listen_retry(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['listen_retry'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.listen_retry, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['listen_retry'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] "
            "listen_retry of 'abc' cannot be converted to int.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['listen_retry'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.listen_retry, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['listen_retry'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [test] "
            "listen_retry of 'abc' cannot be converted to int.")

    def test_parse_conf_eventlet_hub(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['eventlet_hub'] = 'epolls'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.eventlet_hub.__name__, 'eventlet.hubs.epolls')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['eventlet_hub'] = 'epolls'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.eventlet_hub.__name__, 'eventlet.hubs.epolls')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['eventlet_hub'] = 'eventlet.hubs.epolls'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.eventlet_hub.__name__, 'eventlet.hubs.epolls')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['eventlet_hub'] = 'invalid'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            "Could not load [test] eventlet_hub 'invalid'.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['eventlet_hub'] = 'invalid.module'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            "Could not load [test] eventlet_hub 'invalid.module'.")

    def test_parse_conf_workers(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['workers'] = '2'
        ss._parse_conf(Conf(confd))
        if self._override_workers is None:
            self.assertEquals(ss.worker_count, 2)
            self.assertEquals(ss.worker_names, ['0', '1'])
        else:
            self.assertEquals(ss.worker_count, self._override_workers)
            self.assertEquals(ss.worker_names,
                              [str(x) for x in xrange(self._override_workers)])

        ss = self._class(FakeServer(no_daemon=True), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['workers'] = '2'
        ss._parse_conf(Conf(confd))
        if self._override_workers is None:
            self.assertEquals(ss.worker_count, 0)
            self.assertEquals(ss.worker_names, ['0'])
        else:
            self.assertEquals(ss.worker_count, self._override_workers)
            self.assertEquals(ss.worker_names,
                              [str(x) for x in xrange(self._override_workers)])

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['workers'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] workers of "
            "'abc' cannot be converted to int.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {}).update({'workers': '2'})
        ss._parse_conf(Conf(confd))
        if self._override_workers is None:
            self.assertEquals(ss.worker_count, 2)
            self.assertEquals(ss.worker_names, ['0', '1'])
        else:
            self.assertEquals(ss.worker_count, self._override_workers)
            self.assertEquals(ss.worker_names,
                              [str(x) for x in xrange(self._override_workers)])

        ss = self._class(FakeServer(no_daemon=True), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {}).update({'workers': '2'})
        ss._parse_conf(Conf(confd))
        if self._override_workers is None:
            self.assertEquals(ss.worker_count, 0)
            self.assertEquals(ss.worker_names, ['0'])
        else:
            self.assertEquals(ss.worker_count, self._override_workers)
            self.assertEquals(ss.worker_names,
                              [str(x) for x in xrange(self._override_workers)])

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['workers'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [test] workers of "
            "'abc' cannot be converted to int.")


class AppWithInvalidInit(object):

    def __init__(self):
        pass


class AppWithInvalidCall(object):

    def __init__(self, name, conf, next_app):
        pass

    def __call__(self):
        pass


class AppWithNoCall(object):

    def __init__(self, name, conf, next_app):
        pass


class AppWithInvalidParseConf1(object):

    def __init__(self, name, conf, next_app):
        pass

    def __call__(self, env, start_response):
        pass

    @classmethod
    def parse_conf(cls):
        pass


class AppWithInvalidParseConf2(object):

    parse_conf = 'blah'

    def __init__(self, name, conf, next_app):
        pass

    def __call__(self, env, start_response):
        pass


class AppWithNoParseConf(object):

    def __init__(self, name, conf, next_app):
        pass

    def __call__(self, env, start_response):
        pass


class AppWithParseConf(object):

    def __init__(self, name, conf, next_app):
        pass

    def __call__(self, env, start_response):
        pass

    @classmethod
    def parse_conf(cls, name, conf):
        return {'ok': True}


class AppWithInvalidStatsConf1(object):

    def __init__(self, name, conf, next_app):
        pass

    def __call__(self, env, start_response):
        pass

    @classmethod
    def stats_conf(cls):
        pass


class AppWithInvalidStatsConf2(object):

    stats_conf = 'blah'

    def __init__(self, name, conf, next_app):
        pass

    def __call__(self, env, start_response):
        pass


class AppWithNoStatsConf(object):

    def __init__(self, name, conf, next_app):
        pass

    def __call__(self, env, start_response):
        pass


class AppWithStatsConf(object):

    def __init__(self, name, conf, next_app):
        pass

    def __call__(self, env, start_response):
        if env['PATH_INFO'] == '/exception':
            raise Exception('testing')
        start_response('200 OK', [('Content-Length', '0')])
        return []

    @classmethod
    def stats_conf(cls, name, conf):
        return [('ok', 'sum')]


class FakeLogger(object):

    def __init__(self):
        self.debug_calls = []
        self.info_calls = []
        self.notice_calls = []
        self.error_calls = []
        self.exception_calls = []

    def debug(self, *args):
        self.debug_calls.append(args)

    def info(self, *args):
        self.info_calls.append(args)

    def notice(self, *args):
        self.notice_calls.append(args)

    def error(self, *args):
        self.error_calls.append(args)

    def exception(self, *args):
        self.exception_calls.append((args, exc_info()))


class PropertyObject(object):
    pass


class TestWSGISubserver(TestIPSubserver):

    _class = server.WSGISubserver

    def test_init(self):
        ss = TestIPSubserver.test_init(self)
        self.assertEquals(ss.stats_conf.get('request_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_2xx_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_3xx_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_4xx_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_5xx_count'), 'sum')

    def test_parse_conf_defaults(self):
        ss = TestIPSubserver.test_parse_conf_defaults(self)
        self.assertEquals(ss.log_headers, False)
        self.assertEquals(ss.count_status_codes, [404, 408, 499, 501])
        self.assertEquals(ss.wsgi_input_iter_chunk_size, 4096)
        self.assertEquals(ss.apps, [])

    def test_parse_conf_log_headers(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['log_headers'] = 'yes'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.log_headers, True)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['log_headers'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] "
            "log_headers of 'abc' cannot be converted to boolean.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['log_headers'] = 'yes'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.log_headers, True)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['log_headers'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [test] "
            "log_headers of 'abc' cannot be converted to boolean.")

    def test_parse_conf_count_status_codes(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['count_status_codes'] = '1'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.count_status_codes, [1])

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['count_status_codes'] = '1 2 345'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.count_status_codes, [1, 2, 345])
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['count_status_codes'] = 'abc'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid [test] count_status_codes 'abc'.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['count_status_codes'] = '1'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.count_status_codes, [1])

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['count_status_codes'] = '1 2 345'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.count_status_codes, [1, 2, 345])
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['count_status_codes'] = 'abc'
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid [test] count_status_codes 'abc'.")

    def test_parse_conf_wsgi_input_iter_chunk_size(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['wsgi_input_iter_chunk_size'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.wsgi_input_iter_chunk_size, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['wsgi_input_iter_chunk_size'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] "
            "wsgi_input_iter_chunk_size of 'abc' cannot be converted to int.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['wsgi_input_iter_chunk_size'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.wsgi_input_iter_chunk_size, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['wsgi_input_iter_chunk_size'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [test] "
            "wsgi_input_iter_chunk_size of 'abc' cannot be converted to int.")

    def test_configure_wsgi_apps(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one two'
        confd.setdefault('one', {})['call'] = 'brim.wsgi_echo.WSGIEcho'
        confd.setdefault('two', {})['call'] = 'brim.wsgi_echo.WSGIEcho'
        conf = Conf(confd)
        ss._parse_conf(conf)
        self.assertEquals(len(ss.apps), 2)
        self.assertEquals(ss.apps[0][0], 'one')
        self.assertEquals(ss.apps[1][0], 'two')
        self.assertEquals(ss.apps[0][1].__name__, 'WSGIEcho')
        self.assertEquals(ss.apps[1][1].__name__, 'WSGIEcho')
        self.assertEquals(ss.apps[0][2], ss.apps[0][1].parse_conf('one', conf))
        self.assertEquals(ss.apps[1][2], ss.apps[1][1].parse_conf('two', conf))

    def test_configure_wsgi_apps_conf_no_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['cll'] = 'brim.wsgi_echo.WSGIEcho'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
                          "App [one] not configured with 'call' option.")

    def test_configure_wsgi_apps_conf_invalid_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = 'brim_wsgi_echo_WSGIEcho'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid call value "
            "'brim_wsgi_echo_WSGIEcho' for app [one].")

    def test_configure_wsgi_apps_no_load(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = 'brim.wsgi_echo.sgi_cho'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Could not load class "
            "'brim.wsgi_echo.sgi_cho' for app [one].")

    def test_configure_wsgi_apps_not_a_class(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = 'brim.server._send_pid_sig'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to instantiate "
            "'brim.server._send_pid_sig' for app [one]. Probably not a "
            "class.")

    def test_configure_wsgi_apps_invalid_init(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithInvalidInit'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to instantiate "
            "'brim.test.unit.test_server.AppWithInvalidInit' for app "
            "[one]. Incorrect number of args, 1, should be 4 (self, name, "
            "conf, next_app).")

    def test_configure_wsgi_apps_invalid_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithInvalidCall'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to use "
            "'brim.test.unit.test_server.AppWithInvalidCall' for app "
            "[one]. Incorrect number of __call__ args, 1, should be 3 (self, "
            "env, start_response).")

    def test_configure_wsgi_apps_no_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithNoCall'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to use "
            "'brim.test.unit.test_server.AppWithNoCall' for app "
            "[one]. Probably no __call__ method.")

    def test_configure_wsgi_apps_invalid_parse_conf1(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithInvalidParseConf1'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.AppWithInvalidParseConf1' for "
            "app [one]. Incorrect number of parse_conf args, 1, should be "
            "3 (cls, name, conf).")

    def test_configure_wsgi_apps_invalid_parse_conf2(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithInvalidParseConf2'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.AppWithInvalidParseConf2' for "
            "app [one]. parse_conf probably not a method.")

    def test_configure_wsgi_apps_no_parse_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithNoParseConf'
        conf = Conf(confd)
        ss._parse_conf(conf)
        self.assertEquals(ss.apps[0][2], conf)

    def test_configure_wsgi_apps_with_parse_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithParseConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.apps[0][2], {'ok': True})

    def test_configure_wsgi_apps_invalid_stats_conf1(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithInvalidStatsConf1'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.AppWithInvalidStatsConf1' for "
            "app [one]. Incorrect number of stats_conf args, 1, should be 3 "
            "(cls, name, conf).")

    def test_configure_wsgi_apps_invalid_stats_conf2(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithInvalidStatsConf2'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.AppWithInvalidStatsConf2' for "
            "app [one]. stats_conf probably not a method.")

    def test_configure_wsgi_apps_no_stats_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithNoStatsConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.stats_conf.get('start_time'), 'worker')
        self.assertEquals(ss.stats_conf.get('request_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_2xx_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_3xx_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_4xx_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_5xx_count'), 'sum')

    def test_configure_wsgi_apps_with_stats_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['apps'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.AppWithStatsConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.stats_conf.get('start_time'), 'worker')
        self.assertEquals(ss.stats_conf.get('request_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_2xx_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_3xx_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_4xx_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('status_5xx_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('ok'), 'sum')

    def test_privileged_start(self):
        ss = self._class(FakeServer(), 'test')
        ss._parse_conf(Conf(self._get_default_confd()))
        exc = None
        try:
            ss._privileged_start()
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            'Could not bind to *:80: [Errno 13] Permission denied')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['port'] = '0'
        ss._parse_conf(Conf(confd))
        ss._privileged_start()
        self.assertTrue(ss.sock is not None)

        get_listening_tcp_socket_calls = []

        def _get_listening_tcp_socket(*args, **kwargs):
            get_listening_tcp_socket_calls.append((args, kwargs))
            return 'sock'

        ss = self._class(FakeServer(), 'test')
        ss._parse_conf(Conf(self._get_default_confd()))
        get_listening_tcp_socket_orig = server.get_listening_tcp_socket
        try:
            server.get_listening_tcp_socket = _get_listening_tcp_socket
            ss._privileged_start()
        finally:
            server.get_listening_tcp_socket = get_listening_tcp_socket_orig
        self.assertEquals(ss.sock, 'sock')
        self.assertEquals(get_listening_tcp_socket_calls, [(('*', 80), {
            'keyfile': None, 'style': 'eventlet', 'retry': 30,
            'certfile': None, 'backlog': 4096})])

    def test_start(self, output=False):
        capture_exceptions_stdout_stderr_calls = []
        time_calls = []
        get_logger_calls = []
        fake_logger = FakeLogger()
        fake_wsgi = PropertyObject()
        fake_wsgi.HttpProtocol = PropertyObject()
        sustain_workers_calls = []
        shutdown_safe_calls = []

        def _capture_exceptions_stdout_stderr(*args, **kwargs):
            capture_exceptions_stdout_stderr_calls.append((args, kwargs))

        def _time(*args):
            time_calls.append(args)
            return len(time_calls)

        def _get_logger(*args):
            get_logger_calls.append(args)
            return fake_logger

        def _sustain_workers(*args, **kwargs):
            sustain_workers_calls.append((args, kwargs))

        def _shutdown_safe(*args):
            shutdown_safe_calls.append(args)

        capture_exceptions_stdout_stderr_orig = \
            server.capture_exceptions_stdout_stderr
        time_orig = server.time
        get_logger_orig = server.get_logger
        wsgi_orig = server.wsgi
        sustain_workers_orig = server.sustain_workers
        shutdown_safe_orig = server.shutdown_safe
        try:
            server.capture_exceptions_stdout_stderr = \
                _capture_exceptions_stdout_stderr
            server.time = _time
            server.get_logger = _get_logger
            server.wsgi = fake_wsgi
            server.sustain_workers = _sustain_workers
            server.shutdown_safe = _shutdown_safe
            ss = TestIPSubserver.test_start(self, output=output)
        finally:
            server.capture_exceptions_stdout_stderr = \
                capture_exceptions_stdout_stderr_orig
            server.time = time_orig
            server.get_logger = get_logger_orig
            server.wsgi = wsgi_orig
            server.sustain_workers = sustain_workers_orig
            server.shutdown_safe = shutdown_safe_orig

        if output:
            self.assertEquals(capture_exceptions_stdout_stderr_calls, [])
        else:
            self.assertEquals(capture_exceptions_stdout_stderr_calls, [((),
                {'exceptions': ss._capture_exception,
                 'stdout_func': ss._capture_stdout,
                 'stderr_func': ss._capture_stderr})])
        self.assertEquals(time_calls, [()])
        self.assertEquals(get_logger_calls, [(ss.name, ss.log_name,
            ss.log_level, ss.log_facility, ss.server.no_daemon)])
        self.assertEquals(sustain_workers_calls, [((1, ss._wsgi_worker),
                                                   {'logger': fake_logger})])
        self.assertEquals(shutdown_safe_calls, [(ss.sock,)])
        self.assertEquals(ss.worker_id, -1)
        self.assertEquals(ss.start_time, 1)
        self.assertEquals(ss.logger, fake_logger)
        for code in ss.count_status_codes:
            key = 'status_%d_count' % code
            self.assertEquals(ss.stats_conf.get(key), 'sum',
                'key %r value %r != %r' % (key, ss.stats_conf.get(key), 'sum'))
        self.assertEquals(fake_wsgi.HttpProtocol.default_request_version,
                          'HTTP/1.0')
        self.assertEquals(fake_wsgi.HttpProtocol.log_request('blah'), None)
        self.assertEquals(fake_logger.error_calls, [])
        fake_wsgi.HttpProtocol.log_message(None, 'test message')
        self.assertEquals(fake_logger.error_calls,
                          [('WSGI ERROR: test message',)])
        self.assertEquals(fake_wsgi.WRITE_TIMEOUT, ss.client_timeout)

    def test_start_with_output(self):
        self.test_start(output=True)

    def test_wsgi_worker(self, no_setproctitle=False, no_daemon=False,
                         with_apps=False, raises=False):
        setproctitle_calls = []
        use_hub_calls = []
        fake_wsgi = PropertyObject()
        fake_wsgi.HttpProtocol = PropertyObject()
        server_calls = []

        def _setproctitle(*args):
            setproctitle_calls.append(args)

        def _sustain_workers(*args, **kwargs):
            pass

        def _use_hub(*args):
            use_hub_calls.append(args)

        def _server(*args, **kwargs):
            server_calls.append((args, kwargs))
            if raises == 'socket einval':
                err = server.socket_error('test socket einval')
                err.errno = server.EINVAL
                raise err
            elif raises == 'socket other':
                raise server.socket_error('test socket other')
            elif raises == 'other':
                raise Exception('test other')

        def _time():
            return 1

        setproctitle_orig = server.setproctitle
        sustain_workers_orig = server.sustain_workers
        use_hub_orig = server.use_hub
        wsgi_orig = server.wsgi
        time_orig = server.time
        fake_wsgi.server = _server
        exc = None
        try:
            server.setproctitle = None if no_setproctitle else _setproctitle
            server.sustain_workers = _sustain_workers
            server.use_hub = _use_hub
            server.wsgi = fake_wsgi
            server.time = _time
            ss = self._class(FakeServer(no_daemon=no_daemon, output=True),
                             'test')
            if with_apps:
                confd = self._get_default_confd()
                confd.setdefault('test', {})['port'] = '0'
                confd['test']['apps'] = 'one two'
                confd.setdefault('one', {})['call'] = 'brim.wsgi_echo.WSGIEcho'
                confd.setdefault('two', {})['call'] = 'brim.wsgi_echo.WSGIEcho'
            else:
                confd = self._get_default_confd()
                confd.setdefault('test', {})['port'] = '0'
            ss._parse_conf(Conf(confd))
            ss._privileged_start()
            bs = server._BucketStats(['0'], {'start_time': 'worker'})
            ss._start(bs)
            ss._wsgi_worker(0)
        except Exception, err:
            exc = err
        finally:
            server.setproctitle = setproctitle_orig
            server.sustain_workers = sustain_workers_orig
            server.use_hub = use_hub_orig
            server.wsgi = wsgi_orig
            server.time = time_orig

        if no_setproctitle or no_daemon:
            self.assertEquals(setproctitle_calls, [])
        else:
            self.assertEquals(setproctitle_calls, [('0:test:brimd',)])
        self.assertEquals(ss.worker_id, 0)
        self.assertEquals(ss.bucket_stats.get(ss.worker_id, 'start_time'), 1)
        if no_daemon:
            self.assertEquals(use_hub_calls, [])
        else:
            self.assertEquals(use_hub_calls, [(None,)])
        if with_apps:
            self.assertEquals(ss.first_app.__class__.__name__, 'WSGIEcho')
            self.assertEquals(ss.first_app.name, 'one')
            self.assertEquals(ss.first_app.next_app.name, 'two')
            self.assertEquals(ss.first_app.next_app.next_app, ss)
        else:
            self.assertEquals(ss.first_app, ss)
        self.assertEquals(len(server_calls), 1)
        self.assertEquals(len(server_calls[0]), 2)
        self.assertEquals(len(server_calls[0][0]), 3)
        null_logger = server_calls[0][0][2]
        self.assertEquals(null_logger.__class__.__name__,
                          '_EventletWSGINullLogger')
        pool = server_calls[0][1]['custom_pool']
        self.assertEquals(pool.size, ss.concurrent_per_worker)
        self.assertEquals(server_calls, [(
            (ss.sock, ss._wsgi_entry, null_logger),
            {'custom_pool': pool})])
        if raises == 'socket einval':
            self.assertEquals(exc, None)
        elif raises == 'socket other':
            self.assertEquals(str(exc), 'test socket other')
        elif raises == 'other':
            self.assertEquals(str(exc), 'test other')
        else:
            self.assertEquals(exc, None)

    def test_wsgi_worker_no_setproctitle(self):
        self.test_wsgi_worker(no_setproctitle=True)

    def test_wsgi_worker_no_daemon(self):
        self.test_wsgi_worker(no_daemon=True)

    def test_wsgi_worker_with_apps(self):
        self.test_wsgi_worker(with_apps=True)

    def test_wsgi_worker_raises_socket_einval(self):
        self.test_wsgi_worker(raises='socket einval')

    def test_wsgi_worker_raises_socket_other(self):
        self.test_wsgi_worker(raises='socket other')

    def test_wsgi_worker_raises_other(self):
        self.test_wsgi_worker(raises='other')

    def test_wsgi_entry(self, with_app=False, raises=False):
        ss = self._class(FakeServer(output=True), 'test')
        if with_app:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['port'] = '0'
            confd['test']['apps'] = 'one'
            confd.setdefault('one', {})['call'] = 'brim.wsgi_echo.WSGIEcho'
        else:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['port'] = '0'
        ss._parse_conf(Conf(confd))
        ss._privileged_start()
        bs = server._BucketStats(['0'], {'start_time': 'worker'})

        def _sustain_workers(*args, **kwargs):
            pass

        def _server(*args, **kwargs):
            pass

        sustain_workers_orig = server.sustain_workers
        wsgi_orig = server.wsgi
        try:
            server.sustain_workers = _sustain_workers
            server.wsgi = PropertyObject()
            server.wsgi.HttpProtocol = PropertyObject()
            server.wsgi.server = _server
            ss._start(bs)
            ss._wsgi_worker(0)
        finally:
            server.sustain_workers = sustain_workers_orig
            server.wsgi = wsgi_orig

        start_response_calls = []
        log_request_calls = []
        uuid4_instance = uuid4()

        def _start_response(*args, **kwargs):
            start_response_calls.append((args, kwargs))

        def _uuid4():
            return uuid4_instance

        def _time():
            return 1

        def _log_request(*args, **kwargs):
            log_request_calls.append((args, kwargs))

        def _app_with_body_exception(env, start_response):
            start_response('200 OK', [('Content-Length', '10')])
            yield 'partial'
            raise Exception('body exception')

        uuid4_orig = server.uuid4
        time_orig = server.time
        env = {'PATH_INFO': '/echo', 'wsgi.input': StringIO('test value')}
        try:
            server.uuid4 = _uuid4
            server.time = _time
            ss._log_request = _log_request
            if raises == 'start':
                ss.first_app = 'i will raise an exception'
            elif raises == 'body':
                ss.first_app = _app_with_body_exception
            ss.logger = FakeLogger()
            content = ''.join(ss._wsgi_entry(env, _start_response))
        finally:
            server.uuid4 = uuid4_orig
            server.time = time_orig

        self.assertEquals(env.get('brim'), ss)
        self.assertEquals(env.get('brim.start'), 1)
        self.assertEquals(env.get('brim.stats').bucket_stats, ss.bucket_stats)
        self.assertEquals(env.get('brim.stats').bucket_id, ss.worker_id)
        self.assertEquals(env.get('brim.logger'), ss.logger)
        self.assertEquals(env.get('brim.txn'), uuid4_instance.hex)
        if with_app:
            self.assertEquals(env.get('brim._bytes_in'), 10)
            self.assertEquals(env.get('brim._bytes_out'), 10)
        else:
            self.assertEquals(env.get('brim._bytes_in'), 0)
            if raises == 'body':
                self.assertEquals(env.get('brim._bytes_out'), 7)
            else:
                self.assertEquals(env.get('brim._bytes_out'), 0)
        wi = env.get('wsgi.input')
        self.assertEquals(wi.__class__.__name__, '_WsgiInput')
        self.assertEquals(wi.env, env)
        self.assertEquals(wi.iter_chunk_size, ss.wsgi_input_iter_chunk_size)
        self.assertEquals(env.get('brim.additional_request_log_info'), [])
        self.assertEquals(env.get('brim.json_dumps'), ss.json_dumps)
        self.assertEquals(env.get('brim.json_loads'), ss.json_loads)
        if raises:
            if raises == 'start':
                self.assertEquals(env.get('brim._start_response'),
                    ('500 Internal Server Error', [('Content-Length', '0')],
                     None))
                self.assertEquals(content, '')
            else:
                self.assertEquals(env.get('brim._start_response'),
                    ('200 OK', [('Content-Length', '10')], None))
                self.assertEquals(content, 'partial')
            self.assertEquals(ss.logger.debug_calls, [])
            self.assertEquals(ss.logger.info_calls, [])
            self.assertEquals(ss.logger.notice_calls, [])
            self.assertEquals(ss.logger.error_calls, [])
            self.assertEquals(len(ss.logger.exception_calls), 1)
            self.assertEquals(len(ss.logger.exception_calls[0]), 2)
            self.assertEquals(ss.logger.exception_calls[0][0],
                              ('WSGI EXCEPTION:',))
            self.assertEquals(len(ss.logger.exception_calls[0][1]), 3)
            if raises == 'start':
                self.assertEquals(str(ss.logger.exception_calls[0][1][1]),
                                  "'str' object is not callable")
            else:
                self.assertEquals(str(ss.logger.exception_calls[0][1][1]),
                                  'body exception')
        elif with_app:
            self.assertEquals(env.get('brim._start_response'),
                ('200 OK', [('Content-Length', '10')], None))
            self.assertEquals(content, 'test value')
            self.assertEquals(ss.logger.debug_calls, [])
            self.assertEquals(ss.logger.info_calls, [])
            self.assertEquals(ss.logger.notice_calls, [])
            self.assertEquals(ss.logger.error_calls, [])
            self.assertEquals(ss.logger.exception_calls, [])
        else:
            self.assertEquals(env.get('brim._start_response'),
                ('404 Not Found', [('Content-Length', '0')], None))
            self.assertEquals(content, '')
            self.assertEquals(ss.logger.debug_calls, [])
            self.assertEquals(ss.logger.info_calls, [])
            self.assertEquals(ss.logger.notice_calls, [])
            self.assertEquals(ss.logger.error_calls, [])
            self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(log_request_calls, [((env,), {})])

    def test_wsgi_entry_with_apps(self):
        self.test_wsgi_entry(with_app=True)

    def test_wsgi_entry_raises_start_exception(self):
        self.test_wsgi_entry(raises='start')

    def test_wsgi_entry_raises_body_exception(self):
        self.test_wsgi_entry(raises='body')

    def _log_request_build(self, start=1330037777.77):
        return {'REQUEST_METHOD': 'GET',
                'PATH_INFO': '/path',
                'SERVER_PROTOCOL': 'HTTP/1.1',
                'brim.start': start,
                'brim.txn': 'abcdef',
                'brim._start_response':
                     ('200 OK', [('Content-Length', '10')], None),
                'brim._bytes_in': 0,
                'brim._bytes_out': 10}

    def _log_request_execute(self, env, end=1330037779.89, log_headers=False):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.log_headers = log_headers
        ss.bucket_stats = server._BucketStats(['test'], {
            'request_count': 'sum', 'status_2xx_count': 'sum',
            'status_200_count': 'sum', 'status_201_count': 'sum',
            'status_3xx_count': 'sum', 'status_4xx_count': 'sum',
            'status_5xx_count': 'sum'})
        ss.worker_id = 0

        time_orig = server.time
        gmtime_orig = server.gmtime

        def _time():
            return end

        def _gmtime():
            return gmtime_orig(end)

        try:
            server.time = _time
            server.gmtime = _gmtime
            ss._log_request(env)
        finally:
            server.time = time_orig
            server.gmtime = gmtime_orig

        return ss

    def test_log_request_no_start_response(self):
        env = self._log_request_build()
        del env['brim._start_response']
        env['brim._bytes_out'] = 0
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 499 - - - - abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_minimal(self):
        env = self._log_request_build()
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 200 10 - - - abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_3xx(self):
        env = self._log_request_build()
        env['brim._start_response'] = \
            ('301 Test', [('Content-Length', '10')], None)
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 301 10 - - - abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_4xx(self):
        env = self._log_request_build()
        env['brim._start_response'] = \
            ('404 Test', [('Content-Length', '10')], None)
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 404 10 - - - abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_5xx(self):
        env = self._log_request_build()
        env['brim._start_response'] = \
            ('503 Test', [('Content-Length', '10')], None)
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 1)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 503 10 - - - abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_exception(self):
        env = self._log_request_build()
        del env['PATH_INFO']
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(len(ss.logger.exception_calls), 1)
        self.assertEquals(len(ss.logger.exception_calls[0]), 2)
        self.assertEquals(ss.logger.exception_calls[0][0],
                          ('WSGI EXCEPTION:',))
        self.assertEquals(len(ss.logger.exception_calls[0][1]), 3)
        self.assertEquals(str(ss.logger.exception_calls[0][1][1]),
                          "'PATH_INFO'")
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_path_quoted_requoted(self):
        env = self._log_request_build()
        env['PATH_INFO'] = '/path%20%2Ftest'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path%20/test HTTP/1.1 200 10 - - - abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_query(self):
        env = self._log_request_build()
        env['QUERY_STRING'] = 'param1=value1+value2&param2'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path?param1=value1%20value2&param2 HTTP/1.1 200 10 - - - '
            'abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_cluster_client(self):
        env = self._log_request_build()
        env['HTTP_X_CLUSTER_CLIENT_IP'] = '1.2.3.4'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('1.2.3.4 - - - '
            '20120223T225619Z GET /path HTTP/1.1 200 10 - - - '
            'abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_forwarded_for(self):
        env = self._log_request_build()
        env['HTTP_X_FORWARDED_FOR'] = '1.2.3.4, 1.2.3.5'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('1.2.3.4 - - - '
            '20120223T225619Z GET /path HTTP/1.1 200 10 - - - '
            'abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_cluster_client_forwarded_for(self):
        env = self._log_request_build()
        env['HTTP_X_CLUSTER_CLIENT_IP'] = '1.2.3.4'
        env['HTTP_X_FORWARDED_FOR'] = '1.2.3.5, 1.2.3.6'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('1.2.3.4 - - - '
            '20120223T225619Z GET /path HTTP/1.1 200 10 - - - '
            'abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_remote_addr(self):
        env = self._log_request_build()
        env['REMOTE_ADDR'] = '1.2.3.4'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('1.2.3.4 1.2.3.4 - - '
            '20120223T225619Z GET /path HTTP/1.1 200 10 - - - '
            'abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_remote_addr_cluster_client(self):
        env = self._log_request_build()
        env['REMOTE_ADDR'] = '1.2.3.4'
        env['HTTP_X_CLUSTER_CLIENT_IP'] = '1.2.3.5'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('1.2.3.5 1.2.3.4 - - '
            '20120223T225619Z GET /path HTTP/1.1 200 10 - - - '
            'abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_remote_addr_forwarded_for(self):
        env = self._log_request_build()
        env['REMOTE_ADDR'] = '1.2.3.4'
        env['HTTP_X_FORWARDED_FOR'] = '1.2.3.5, 1.2.3.6'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('1.2.3.5 1.2.3.4 - - '
            '20120223T225619Z GET /path HTTP/1.1 200 10 - - - '
            'abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_remote_addr_cluster_client_forwarded_for(self):
        env = self._log_request_build()
        env['REMOTE_ADDR'] = '1.2.3.4'
        env['HTTP_X_CLUSTER_CLIENT_IP'] = '1.2.3.5'
        env['HTTP_X_FORWARDED_FOR'] = '1.2.3.6, 1.2.3.7'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('1.2.3.5 1.2.3.4 - - '
            '20120223T225619Z GET /path HTTP/1.1 200 10 - - - '
            'abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_headers(self):
        env = self._log_request_build()
        env['HTTP_CONTENT_TYPE'] = 'text/plain'
        env['HTTP_X_TEST'] = 'test value'
        ss = self._log_request_execute(env, log_headers=True)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 200 10 - - - abcdef 2.12000 headers: '
            'X-Test:test%20value%0AContent-Type:text/plain',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_client_disconnect(self):
        env = self._log_request_build()
        env['brim._client_disconnect'] = True
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 499 10 - - - abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_goofy_code(self):
        env = self._log_request_build()
        env['brim._start_response'] = \
            ('2xx OK', [('Content-Length', '10')], None)
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 - 10 - - - abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_auth_token(self):
        env = self._log_request_build()
        env['HTTP_X_AUTH_TOKEN'] = 'authtoken'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - authtoken - '
            '20120223T225619Z GET /path HTTP/1.1 200 10 - - - abcdef '
            '2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_bytes_in(self):
        env = self._log_request_build()
        env['brim._bytes_in'] = 123
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 200 10 123 - - abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_referer(self):
        env = self._log_request_build()
        env['HTTP_REFERER'] = 'http://some.host/path%20/test?maybe=query+value'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 200 10 - '
            'http://some.host/path%2520/test?maybe=query+value - abcdef '
            '2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_user_agent(self):
        env = self._log_request_build()
        env['HTTP_USER_AGENT'] = 'Some User Agent (v1.0)'
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 200 10 - - Some%20User%20Agent%20(v1.0) '
            'abcdef 2.12000',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_additional_info(self):
        env = self._log_request_build()
        env['brim.additional_request_log_info'] = ['test:', 'one', 'two']
        ss = self._log_request_execute(env)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 200 10 - - - abcdef 2.12000 test: one two',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_log_request_additional_info_and_headers(self):
        env = self._log_request_build()
        env['brim.additional_request_log_info'] = ['test:', 'one', 'two']
        env['HTTP_CONTENT_TYPE'] = 'text/plain'
        ss = self._log_request_execute(env, log_headers=True)
        self.assertEquals(ss.bucket_stats.get(0, 'request_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_2xx_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_200_count'), 1)
        self.assertEquals(ss.bucket_stats.get(0, 'status_201_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_3xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_4xx_count'), 0)
        self.assertEquals(ss.bucket_stats.get(0, 'status_5xx_count'), 0)
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [('- - - - 20120223T225619Z '
            'GET /path HTTP/1.1 200 10 - - - abcdef 2.12000 test: one two '
            'headers: Content-Type:text/plain',)])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])
        self.assertEquals(ss.logger.txn, None)

    def test_capture_exception(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_exception(*exc_info())
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls,
                          [("UNCAUGHT EXCEPTION: wid:123 None ['None']",)])
        self.assertEquals(ss.logger.exception_calls, [])

        ss.logger = FakeLogger()
        try:
            raise Exception('test')
        except Exception:
            ss._capture_exception(*exc_info())
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(len(ss.logger.error_calls), 1)
        self.assertEquals(len(ss.logger.error_calls[0]), 1)
        e = ss.logger.error_calls[0][0]
        self.assertTrue(e.startswith("UNCAUGHT EXCEPTION: wid:123 Exception: "
            "test ['Traceback (most recent call last):', '  File "))
        self.assertTrue(e.endswith('\', "    raise Exception(\'test\')", '
            '\'Exception: test\']'))
        self.assertEquals(ss.logger.exception_calls, [])

    def test_capture_stdout(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_stdout('one\ntwo three\nfour\n')
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [('STDOUT: wid:123 one',),
            ('STDOUT: wid:123 two three',), ('STDOUT: wid:123 four',)])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])

    def test_capture_stderr(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_stderr('one\ntwo three\nfour\n')
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls, [('STDERR: wid:123 one',),
            ('STDERR: wid:123 two three',), ('STDERR: wid:123 four',)])
        self.assertEquals(ss.logger.exception_calls, [])


class TCPWithInvalidInit(object):

    def __init__(self):
        pass


class TCPWithInvalidCall(object):

    def __init__(self, name, conf):
        pass

    def __call__(self):
        pass


class TCPWithNoCall(object):

    def __init__(self, name, conf):
        pass


class TCPWithInvalidParseConf1(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, ip, port):
        pass

    @classmethod
    def parse_conf(cls):
        pass


class TCPWithInvalidParseConf2(object):

    parse_conf = 'blah'

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, ip, port):
        pass


class TCPWithNoParseConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, ip, port):
        pass


class TCPWithParseConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, ip, port):
        pass

    @classmethod
    def parse_conf(cls, name, conf):
        return {'ok': True}


class TCPWithInvalidStatsConf1(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, ip, port):
        pass

    @classmethod
    def stats_conf(cls):
        pass


class TCPWithInvalidStatsConf2(object):

    stats_conf = 'blah'

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, ip, port):
        pass


class TCPWithNoStatsConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, ip, port):
        pass


class TCPWithStatsConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, ip, port):
        pass

    @classmethod
    def stats_conf(cls, name, conf):
        return [('ok', 'sum')]


class TestTCPSubserver(TestIPSubserver):

    _class = server.TCPSubserver

    def _get_default_confd(self):
        return {'test': {'call': 'brim.tcp_echo.TCPEcho'}}

    def test_init(self):
        ss = TestIPSubserver.test_init(self)
        self.assertEquals(ss.stats_conf.get('connection_count'), 'sum')

    def test_parse_conf_defaults(self):
        ss = TestIPSubserver.test_parse_conf_defaults(self)
        self.assertEquals(ss.handler.__name__, 'TCPEcho')

    def test_parse_conf_no_call(self):
        ss = self._class(FakeServer(), 'test')
        conf = Conf({})
        exc = None
        try:
            ss._parse_conf(conf)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
                          "[test] not configured with 'call' option.")

    def test_parse_conf_invalid_call(self):
        ss = self._class(FakeServer(), 'test')
        conf = Conf({'test': {'call': 'invalid'}})
        exc = None
        try:
            ss._parse_conf(conf)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid call value 'invalid' for [test].")

    def test_configure_handler(self):
        ss = self._class(FakeServer(), 'test')
        conf = Conf(self._get_default_confd())
        ss._parse_conf(conf)
        self.assertEquals(ss.handler.__name__, 'TCPEcho')
        self.assertEquals(ss.handler_conf, ss.handler.parse_conf('test', conf))

    def test_configure_handler_no_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['cll'] = confd['test']['call']
        del confd['test']['call']
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
                          "[test] not configured with 'call' option.")

    def test_configure_handler_invalid_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim_tcp_echo_TCPEcho'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            "Invalid call value 'brim_tcp_echo_TCPEcho' for [test].")

    def test_configure_handler_no_load(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.tcp_echo.cp_echo'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            "Could not load class 'brim.tcp_echo.cp_echo' for [test].")

    def test_configure_handler_not_a_class(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.server._send_pid_sig'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to instantiate "
            "'brim.server._send_pid_sig' for [test]. Probably not a class.")

    def test_configure_handler_invalid_init(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.TCPWithInvalidInit'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to instantiate "
            "'brim.test.unit.test_server.TCPWithInvalidInit' for [test]. "
            "Incorrect number of args, 1, should be 3 (self, name, "
            "parsed_conf).")

    def test_configure_handler_invalid_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.TCPWithInvalidCall'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to use "
            "'brim.test.unit.test_server.TCPWithInvalidCall' for [test]. "
            "Incorrect number of __call__ args, 1, should be 6 (self, "
            "subserver, stats, sock, ip, port).")

    def test_configure_handler_no_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.TCPWithNoCall'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to use "
            "'brim.test.unit.test_server.TCPWithNoCall' for [test]. Probably "
            "no __call__ method.")

    def test_configure_handler_invalid_parse_conf1(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = \
            'brim.test.unit.test_server.TCPWithInvalidParseConf1'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.TCPWithInvalidParseConf1' for "
            "[test]. Incorrect number of parse_conf args, 1, should be 3 "
            "(cls, name, conf).")

    def test_configure_handler_invalid_parse_conf2(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = \
            'brim.test.unit.test_server.TCPWithInvalidParseConf2'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.TCPWithInvalidParseConf2' for "
            "[test]. parse_conf probably not a method.")

    def test_configure_handler_no_parse_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.TCPWithNoParseConf'
        conf = Conf(confd)
        ss._parse_conf(conf)
        self.assertEquals(ss.handler_conf, conf)

    def test_configure_handler_with_parse_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.TCPWithParseConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.handler_conf, {'ok': True})

    def test_configure_handler_invalid_stats_conf1(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = \
            'brim.test.unit.test_server.TCPWithInvalidStatsConf1'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.TCPWithInvalidStatsConf1' for "
            "[test]. Incorrect number of stats_conf args, 1, should be 3 "
            "(cls, name, conf).")

    def test_configure_handler_invalid_stats_conf2(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = \
            'brim.test.unit.test_server.TCPWithInvalidStatsConf2'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.TCPWithInvalidStatsConf2' for "
            "[test]. stats_conf probably not a method.")

    def test_configure_handler_no_stats_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.TCPWithNoStatsConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.stats_conf.get('start_time'), 'worker')
        self.assertEquals(ss.stats_conf.get('connection_count'), 'sum')

    def test_configure_handler_with_stats_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.TCPWithStatsConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.stats_conf.get('start_time'), 'worker')
        self.assertEquals(ss.stats_conf.get('connection_count'), 'sum')
        self.assertEquals(ss.stats_conf.get('ok'), 'sum')

    def test_privileged_start(self):
        ss = self._class(FakeServer(), 'test')
        ss._parse_conf(Conf(self._get_default_confd()))
        exc = None
        try:
            ss._privileged_start()
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            'Could not bind to *:80: [Errno 13] Permission denied')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['port'] = '0'
        ss._parse_conf(Conf(confd))
        ss._privileged_start()
        self.assertTrue(ss.sock is not None)

        get_listening_tcp_socket_calls = []

        def _get_listening_tcp_socket(*args, **kwargs):
            get_listening_tcp_socket_calls.append((args, kwargs))
            return 'sock'

        ss = self._class(FakeServer(), 'test')
        ss._parse_conf(Conf(self._get_default_confd()))
        get_listening_tcp_socket_orig = server.get_listening_tcp_socket
        try:
            server.get_listening_tcp_socket = _get_listening_tcp_socket
            ss._privileged_start()
        finally:
            server.get_listening_tcp_socket = get_listening_tcp_socket_orig
        self.assertEquals(ss.sock, 'sock')
        self.assertEquals(get_listening_tcp_socket_calls, [(('*', 80), {
            'keyfile': None, 'style': 'eventlet', 'retry': 30,
            'certfile': None, 'backlog': 4096})])

    def test_start(self, output=False):
        capture_exceptions_stdout_stderr_calls = []
        time_calls = []
        get_logger_calls = []
        fake_logger = FakeLogger()
        sustain_workers_calls = []
        shutdown_safe_calls = []

        def _capture_exceptions_stdout_stderr(*args, **kwargs):
            capture_exceptions_stdout_stderr_calls.append((args, kwargs))

        def _time(*args):
            time_calls.append(args)
            return len(time_calls)

        def _get_logger(*args):
            get_logger_calls.append(args)
            return fake_logger

        def _sustain_workers(*args, **kwargs):
            sustain_workers_calls.append((args, kwargs))

        def _shutdown_safe(*args):
            shutdown_safe_calls.append(args)

        capture_exceptions_stdout_stderr_orig = \
            server.capture_exceptions_stdout_stderr
        time_orig = server.time
        get_logger_orig = server.get_logger
        sustain_workers_orig = server.sustain_workers
        shutdown_safe_orig = server.shutdown_safe
        try:
            server.capture_exceptions_stdout_stderr = \
                _capture_exceptions_stdout_stderr
            server.time = _time
            server.get_logger = _get_logger
            server.sustain_workers = _sustain_workers
            server.shutdown_safe = _shutdown_safe
            ss = TestIPSubserver.test_start(self, output=output)
        finally:
            server.capture_exceptions_stdout_stderr = \
                capture_exceptions_stdout_stderr_orig
            server.time = time_orig
            server.get_logger = get_logger_orig
            server.sustain_workers = sustain_workers_orig
            server.shutdown_safe = shutdown_safe_orig

        if output:
            self.assertEquals(capture_exceptions_stdout_stderr_calls, [])
        else:
            self.assertEquals(capture_exceptions_stdout_stderr_calls, [((),
                {'exceptions': ss._capture_exception,
                 'stdout_func': ss._capture_stdout,
                 'stderr_func': ss._capture_stderr})])
        self.assertEquals(time_calls, [()])
        self.assertEquals(get_logger_calls, [(ss.name, ss.log_name,
            ss.log_level, ss.log_facility, ss.server.no_daemon)])
        self.assertEquals(sustain_workers_calls, [((1, ss._tcp_worker),
                                                   {'logger': fake_logger})])
        self.assertEquals(shutdown_safe_calls, [(ss.sock,)])
        self.assertEquals(ss.worker_id, -1)
        self.assertEquals(ss.start_time, 1)
        self.assertEquals(ss.logger, fake_logger)
        self.assertEquals(fake_logger.error_calls, [])
        self.assertEquals(ss.handler.__class__.__name__, 'TCPEcho')

    def test_start_with_output(self):
        self.test_start(output=True)

    def test_tcp_worker(self, no_setproctitle=False, no_daemon=False,
                        raises=False):
        setproctitle_calls = []
        use_hub_calls = []
        spawn_n_calls = []
        GreenPool_calls = []
        accept_calls = []

        def _setproctitle(*args):
            setproctitle_calls.append(args)

        def _use_hub(*args):
            use_hub_calls.append(args)

        def _spawn_n(*args):
            spawn_n_calls.append(args)
            if raises == 'socket einval':
                err = server.socket_error('test socket einval')
                err.errno = server.EINVAL
                raise err
            elif raises == 'socket other':
                raise server.socket_error('test socket other')
            elif raises == 'other':
                raise Exception('test other')

        def _GreenPool(*args, **kwargs):
            GreenPool_calls.append((args, kwargs))
            rv = PropertyObject()
            rv.spawn_n = _spawn_n
            rv.waitall = lambda *a: None
            return rv

        def _accept(*args):
            accept_calls.append(args)
            if len(accept_calls) == 1:
                return 'sock', ('ip', 'port')
            raise Exception('additional accept')

        def _sustain_workers(*args, **kwargs):
            pass

        def _time():
            return 1

        setproctitle_orig = server.setproctitle
        use_hub_orig = server.use_hub
        GreenPool_orig = server.GreenPool
        sustain_workers_orig = server.sustain_workers
        time_orig = server.time
        exc = None
        try:
            server.setproctitle = None if no_setproctitle else _setproctitle
            server.use_hub = _use_hub
            server.GreenPool = _GreenPool
            server.sustain_workers = _sustain_workers
            server.time = _time
            ss = self._class(FakeServer(no_daemon=no_daemon, output=True),
                             'test')
            confd = self._get_default_confd()
            confd['test']['port'] = '0'
            ss._parse_conf(Conf(confd))
            ss._privileged_start()
            bs = server._BucketStats(['0'], {'start_time': 'worker'})
            ss._start(bs)
            ss.sock.accept = _accept
            ss._tcp_worker(0)
        except Exception, err:
            exc = err
        finally:
            server.setproctitle = setproctitle_orig
            server.use_hub = use_hub_orig
            server.GreenPool = GreenPool_orig
            server.sustain_workers = sustain_workers_orig
            server.time = time_orig

        if no_setproctitle or no_daemon:
            self.assertEquals(setproctitle_calls, [])
        else:
            self.assertEquals(setproctitle_calls, [('0:test:brimd',)])
        self.assertEquals(ss.worker_id, 0)
        self.assertEquals(ss.bucket_stats.get(ss.worker_id, 'start_time'), 1)
        if no_daemon:
            self.assertEquals(use_hub_calls, [])
        else:
            self.assertEquals(use_hub_calls, [(None,)])
        self.assertEquals(ss.handler.__class__.__name__, 'TCPEcho')
        self.assertEquals(GreenPool_calls,
            [((), {'size': ss.concurrent_per_worker})])
        self.assertEquals(len(spawn_n_calls), 1)
        self.assertEquals(len(spawn_n_calls[0]), 6)
        self.assertEquals(spawn_n_calls[0][0].__class__.__name__, 'TCPEcho')
        self.assertEquals(spawn_n_calls[0][1], ss)
        self.assertEquals(spawn_n_calls[0][2].bucket_stats, ss.bucket_stats)
        self.assertEquals(spawn_n_calls[0][3], 'sock')
        self.assertEquals(spawn_n_calls[0][4], 'ip')
        self.assertEquals(spawn_n_calls[0][5], 'port')
        if raises:
            self.assertEquals(accept_calls, [()])
        else:
            self.assertEquals(accept_calls, [(), ()])
        if raises == 'socket einval':
            self.assertEquals(exc, None)
        elif raises == 'socket other':
            self.assertEquals(str(exc), 'test socket other')
        elif raises == 'other':
            self.assertEquals(str(exc), 'test other')
        else:
            self.assertEquals(str(exc), 'additional accept')

    def test_tcp_worker_no_setproctitle(self):
        self.test_tcp_worker(no_setproctitle=True)

    def test_tcp_worker_no_daemon(self):
        self.test_tcp_worker(no_daemon=True)

    def test_tcp_worker_raises_socket_einval(self):
        self.test_tcp_worker(raises='socket einval')

    def test_tcp_worker_raises_socket_other(self):
        self.test_tcp_worker(raises='socket other')

    def test_tcp_worker_raises_other(self):
        self.test_tcp_worker(raises='other')

    def test_capture_exception(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_exception(*exc_info())
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls,
                          [("UNCAUGHT EXCEPTION: tid:123 None ['None']",)])
        self.assertEquals(ss.logger.exception_calls, [])

        ss.logger = FakeLogger()
        try:
            raise Exception('test')
        except Exception:
            ss._capture_exception(*exc_info())
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(len(ss.logger.error_calls), 1)
        self.assertEquals(len(ss.logger.error_calls[0]), 1)
        e = ss.logger.error_calls[0][0]
        self.assertTrue(e.startswith("UNCAUGHT EXCEPTION: tid:123 Exception: "
            "test ['Traceback (most recent call last):', '  File "))
        self.assertTrue(e.endswith('\', "    raise Exception(\'test\')", '
            '\'Exception: test\']'))
        self.assertEquals(ss.logger.exception_calls, [])

    def test_capture_stdout(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_stdout('one\ntwo three\nfour\n')
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [('STDOUT: tid:123 one',),
            ('STDOUT: tid:123 two three',), ('STDOUT: tid:123 four',)])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])

    def test_capture_stderr(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_stderr('one\ntwo three\nfour\n')
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls, [('STDERR: tid:123 one',),
            ('STDERR: tid:123 two three',), ('STDERR: tid:123 four',)])
        self.assertEquals(ss.logger.exception_calls, [])


class UDPWithInvalidInit(object):

    def __init__(self):
        pass


class UDPWithInvalidCall(object):

    def __init__(self, name, conf):
        pass

    def __call__(self):
        pass


class UDPWithNoCall(object):

    def __init__(self, name, conf):
        pass


class UDPWithInvalidParseConf1(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, datagram, ip, port):
        pass

    @classmethod
    def parse_conf(cls):
        pass


class UDPWithInvalidParseConf2(object):

    parse_conf = 'blah'

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, datagram, ip, port):
        pass


class UDPWithNoParseConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, datagram, ip, port):
        pass


class UDPWithParseConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, datagram, ip, port):
        pass

    @classmethod
    def parse_conf(cls, name, conf):
        return {'ok': True}


class UDPWithInvalidStatsConf1(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, datagram, ip, port):
        pass

    @classmethod
    def stats_conf(cls):
        pass


class UDPWithInvalidStatsConf2(object):

    stats_conf = 'blah'

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, datagram, ip, port):
        pass


class UDPWithNoStatsConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, datagram, ip, port):
        pass


class UDPWithStatsConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats, sock, datagram, ip, port):
        pass

    @classmethod
    def stats_conf(cls, name, conf):
        return ['ok']


class TestUDPSubserver(TestIPSubserver):

    _class = server.UDPSubserver
    _override_workers = 1

    def _get_default_confd(self):
        return {'test': {'call': 'brim.udp_echo.UDPEcho'}}

    def test_init(self):
        ss = TestIPSubserver.test_init(self)
        self.assertEquals(ss.stats_conf.get('datagram_count'), 'worker')

    def test_parse_conf_defaults(self):
        ss = TestIPSubserver.test_parse_conf_defaults(self)
        self.assertEquals(ss.handler.__name__, 'UDPEcho')
        self.assertEquals(ss.max_datagram_size, 65536)

    def test_parse_conf_max_datagram_size(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['max_datagram_size'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.max_datagram_size, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('brim', {})['max_datagram_size'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] "
            "max_datagram_size of 'abc' cannot be converted to int.")

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['max_datagram_size'] = '123'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.max_datagram_size, 123)

        ss = self._class(FakeServer(), 'test')
        exc = None
        try:
            confd = self._get_default_confd()
            confd.setdefault('test', {})['max_datagram_size'] = 'abc'
            ss._parse_conf(Conf(confd))
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [test] "
            "max_datagram_size of 'abc' cannot be converted to int.")

    def test_parse_conf_no_call(self):
        ss = self._class(FakeServer(), 'test')
        conf = Conf({})
        exc = None
        try:
            ss._parse_conf(conf)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
                          "[test] not configured with 'call' option.")

    def test_parse_conf_invalid_call(self):
        ss = self._class(FakeServer(), 'test')
        conf = Conf({'test': {'call': 'invalid'}})
        exc = None
        try:
            ss._parse_conf(conf)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid call value 'invalid' for [test].")

    def test_configure_handler(self):
        ss = self._class(FakeServer(), 'test')
        conf = Conf(self._get_default_confd())
        ss._parse_conf(conf)
        self.assertEquals(ss.handler.__name__, 'UDPEcho')
        self.assertEquals(ss.handler_conf, ss.handler.parse_conf('test', conf))

    def test_configure_handler_no_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['cll'] = confd['test']['call']
        del confd['test']['call']
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
                          "[test] not configured with 'call' option.")

    def test_configure_handler_invalid_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim_udp_echo_UDPEcho'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            "Invalid call value 'brim_udp_echo_UDPEcho' for [test].")

    def test_configure_handler_no_load(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.udp_echo.cp_echo'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            "Could not load class 'brim.udp_echo.cp_echo' for [test].")

    def test_configure_handler_not_a_class(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.server._send_pid_sig'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to instantiate "
            "'brim.server._send_pid_sig' for [test]. Probably not a class.")

    def test_configure_handler_invalid_init(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.UDPWithInvalidInit'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to instantiate "
            "'brim.test.unit.test_server.UDPWithInvalidInit' for [test]. "
            "Incorrect number of args, 1, should be 3 (self, name, "
            "parsed_conf).")

    def test_configure_handler_invalid_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.UDPWithInvalidCall'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to use "
            "'brim.test.unit.test_server.UDPWithInvalidCall' for [test]. "
            "Incorrect number of __call__ args, 1, should be 7 (self, "
            "subserver, stats, sock, datagram, ip, port).")

    def test_configure_handler_no_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.UDPWithNoCall'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to use "
            "'brim.test.unit.test_server.UDPWithNoCall' for [test]. Probably "
            "no __call__ method.")

    def test_configure_handler_invalid_parse_conf1(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = \
            'brim.test.unit.test_server.UDPWithInvalidParseConf1'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.UDPWithInvalidParseConf1' for "
            "[test]. Incorrect number of parse_conf args, 1, should be 3 "
            "(cls, name, conf).")

    def test_configure_handler_invalid_parse_conf2(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = \
            'brim.test.unit.test_server.UDPWithInvalidParseConf2'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.UDPWithInvalidParseConf2' for "
            "[test]. parse_conf probably not a method.")

    def test_configure_handler_no_parse_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.UDPWithNoParseConf'
        conf = Conf(confd)
        ss._parse_conf(conf)
        self.assertEquals(ss.handler_conf, conf)

    def test_configure_handler_with_parse_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.UDPWithParseConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.handler_conf, {'ok': True})

    def test_configure_handler_invalid_stats_conf1(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = \
            'brim.test.unit.test_server.UDPWithInvalidStatsConf1'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.UDPWithInvalidStatsConf1' for "
            "[test]. Incorrect number of stats_conf args, 1, should be 3 "
            "(cls, name, conf).")

    def test_configure_handler_invalid_stats_conf2(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = \
            'brim.test.unit.test_server.UDPWithInvalidStatsConf2'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.UDPWithInvalidStatsConf2' for "
            "[test]. stats_conf probably not a method.")

    def test_configure_handler_no_stats_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.UDPWithNoStatsConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.stats_conf.get('start_time'), 'worker')
        self.assertEquals(ss.stats_conf.get('datagram_count'), 'worker')

    def test_configure_handler_with_stats_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd['test']['call'] = 'brim.test.unit.test_server.UDPWithStatsConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.stats_conf.get('start_time'), 'worker')
        self.assertEquals(ss.stats_conf.get('datagram_count'), 'worker')
        self.assertEquals(ss.stats_conf.get('ok'), 'worker')

    def test_privileged_start(self):
        ss = self._class(FakeServer(), 'test')
        ss._parse_conf(Conf(self._get_default_confd()))
        exc = None
        try:
            ss._privileged_start()
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            'Could not bind to *:80: [Errno 13] Permission denied')

        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('brim', {})['port'] = '0'
        ss._parse_conf(Conf(confd))
        ss._privileged_start()
        self.assertTrue(ss.sock is not None)

        get_listening_udp_socket_calls = []

        def _get_listening_udp_socket(*args, **kwargs):
            get_listening_udp_socket_calls.append((args, kwargs))
            return 'sock'

        ss = self._class(FakeServer(), 'test')
        ss._parse_conf(Conf(self._get_default_confd()))
        get_listening_udp_socket_orig = server.get_listening_udp_socket
        try:
            server.get_listening_udp_socket = _get_listening_udp_socket
            ss._privileged_start()
        finally:
            server.get_listening_udp_socket = get_listening_udp_socket_orig
        self.assertEquals(ss.sock, 'sock')
        self.assertEquals(get_listening_udp_socket_calls,
                          [(('*', 80), {'style': 'eventlet', 'retry': 30})])

    def test_start(self, output=False, no_daemon=False, raises=False):
        capture_exceptions_stdout_stderr_calls = []
        time_calls = []
        get_logger_calls = []
        fake_logger = FakeLogger()
        use_hub_calls = []
        spawn_n_calls = []
        GreenPool_calls = []
        recvfrom_calls = []
        ss = [None]

        def _capture_exceptions_stdout_stderr(*args, **kwargs):
            capture_exceptions_stdout_stderr_calls.append((args, kwargs))

        def _time(*args):
            time_calls.append(args)
            return len(time_calls)

        def _get_logger(*args):
            get_logger_calls.append(args)
            return fake_logger

        def _use_hub(*args):
            use_hub_calls.append(args)

        def _spawn_n(*args):
            spawn_n_calls.append(args)
            if raises == 'socket einval':
                err = server.socket_error('test socket einval')
                err.errno = server.EINVAL
                raise err
            elif raises == 'socket other':
                raise server.socket_error('test socket other')
            elif raises == 'other':
                raise Exception('test other')

        def _GreenPool(*args, **kwargs):
            GreenPool_calls.append((args, kwargs))
            rv = PropertyObject()
            rv.spawn_n = _spawn_n
            rv.waitall = lambda *a: None
            return rv

        def _recvfrom(*args):
            recvfrom_calls.append(args)
            if len(recvfrom_calls) == 1:
                return 'datagram', ('ip', 'port')
            raise Exception('additional recvfrom')

        def _func_before_start(created_ss):
            created_ss.sock.recvfrom = _recvfrom
            ss[0] = created_ss

        capture_exceptions_stdout_stderr_orig = \
            server.capture_exceptions_stdout_stderr
        time_orig = server.time
        get_logger_orig = server.get_logger
        use_hub_orig = server.use_hub
        GreenPool_orig = server.GreenPool
        exc = None
        try:
            server.capture_exceptions_stdout_stderr = \
                _capture_exceptions_stdout_stderr
            server.time = _time
            server.get_logger = _get_logger
            server.use_hub = _use_hub
            server.GreenPool = _GreenPool
            bs = server._BucketStats(['0'], {'start_time': 'worker'})
            TestIPSubserver.test_start(self, output=output,
                                       no_daemon=no_daemon,
                                       func_before_start=_func_before_start,
                                       bucket_stats=bs)
        except Exception, err:
            exc = err
        finally:
            server.capture_exceptions_stdout_stderr = \
                capture_exceptions_stdout_stderr_orig
            server.time = time_orig
            server.get_logger = get_logger_orig
            server.use_hub = use_hub_orig
            server.GreenPool = GreenPool_orig

        ss = ss[0]
        self.assertEquals(ss.worker_id, 0)
        if output:
            self.assertEquals(capture_exceptions_stdout_stderr_calls, [])
        else:
            self.assertEquals(capture_exceptions_stdout_stderr_calls, [((),
                {'exceptions': ss._capture_exception,
                 'stdout_func': ss._capture_stdout,
                 'stderr_func': ss._capture_stderr})])
        self.assertEquals(ss.start_time, 1)
        self.assertEquals(time_calls, [()])
        self.assertEquals(get_logger_calls, [(ss.name, ss.log_name,
            ss.log_level, ss.log_facility, ss.server.no_daemon)])
        self.assertEquals(ss.logger, fake_logger)
        self.assertEquals(fake_logger.error_calls, [])
        self.assertEquals(ss.handler.__class__.__name__, 'UDPEcho')
        self.assertEquals(ss.bucket_stats.get(ss.worker_id, 'start_time'), 1)
        if no_daemon:
            self.assertEquals(use_hub_calls, [])
        else:
            self.assertEquals(use_hub_calls, [(None,)])
        self.assertEquals(GreenPool_calls,
            [((), {'size': ss.concurrent_per_worker})])
        self.assertEquals(len(spawn_n_calls), 1)
        self.assertEquals(len(spawn_n_calls[0]), 7)
        self.assertEquals(spawn_n_calls[0][0].__class__.__name__, 'UDPEcho')
        self.assertEquals(spawn_n_calls[0][1], ss)
        self.assertEquals(spawn_n_calls[0][2].bucket_stats, ss.bucket_stats)
        self.assertEquals(spawn_n_calls[0][3], ss.sock)
        self.assertEquals(spawn_n_calls[0][4], 'datagram')
        self.assertEquals(spawn_n_calls[0][5], 'ip')
        self.assertEquals(spawn_n_calls[0][6], 'port')
        if raises:
            self.assertEquals(recvfrom_calls, [(ss.max_datagram_size,)])
        else:
            self.assertEquals(recvfrom_calls,
                [(ss.max_datagram_size,), (ss.max_datagram_size,)])
        if raises == 'socket einval':
            self.assertEquals(exc, None)
        elif raises == 'socket other':
            self.assertEquals(str(exc), 'test socket other')
        elif raises == 'other':
            self.assertEquals(str(exc), 'test other')
        else:
            self.assertEquals(str(exc), 'additional recvfrom')

    def test_start_with_output(self):
        self.test_start(output=True)

    def test_start_no_daemon(self):
        self.test_start(no_daemon=True)

    def test_start_raises_socket_einval(self):
        self.test_start(raises='socket einval')

    def test_start_raises_socket_other(self):
        self.test_start(raises='socket other')

    def test_start_raises_other(self):
        self.test_start(raises='other')

    def test_capture_exception(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_exception(*exc_info())
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls,
                          [("UNCAUGHT EXCEPTION: uid:123 None ['None']",)])
        self.assertEquals(ss.logger.exception_calls, [])

        ss.logger = FakeLogger()
        try:
            raise Exception('test')
        except Exception:
            ss._capture_exception(*exc_info())
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(len(ss.logger.error_calls), 1)
        self.assertEquals(len(ss.logger.error_calls[0]), 1)
        e = ss.logger.error_calls[0][0]
        self.assertTrue(e.startswith("UNCAUGHT EXCEPTION: uid:123 Exception: "
            "test ['Traceback (most recent call last):', '  File "))
        self.assertTrue(e.endswith('\', "    raise Exception(\'test\')", '
            '\'Exception: test\']'))
        self.assertEquals(ss.logger.exception_calls, [])

    def test_capture_stdout(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_stdout('one\ntwo three\nfour\n')
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [('STDOUT: uid:123 one',),
            ('STDOUT: uid:123 two three',), ('STDOUT: uid:123 four',)])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])

    def test_capture_stderr(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_stderr('one\ntwo three\nfour\n')
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls, [('STDERR: uid:123 one',),
            ('STDERR: uid:123 two three',), ('STDERR: uid:123 four',)])
        self.assertEquals(ss.logger.exception_calls, [])


class DaemonWithInvalidInit(object):

    def __init__(self):
        pass


class DaemonWithInvalidCall(object):

    def __init__(self, name, conf):
        pass

    def __call__(self):
        pass


class DaemonWithNoCall(object):

    def __init__(self, name, conf):
        pass


class DaemonWithInvalidParseConf1(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats):
        pass

    @classmethod
    def parse_conf(cls):
        pass


class DaemonWithInvalidParseConf2(object):

    parse_conf = 'blah'

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats):
        pass


class DaemonWithNoParseConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats):
        pass


class DaemonWithParseConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats):
        pass

    @classmethod
    def parse_conf(cls, name, conf):
        return {'ok': True}


class DaemonWithInvalidStatsConf1(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats):
        pass

    @classmethod
    def stats_conf(cls):
        pass


class DaemonWithInvalidStatsConf2(object):

    stats_conf = 'blah'

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats):
        pass


class DaemonWithNoStatsConf(object):

    def __init__(self, name, conf):
        pass

    def __call__(self, subserver, stats):
        pass


class DaemonWithStatsConf(object):

    def __init__(self, name, conf):
        self.calls = []

    def __call__(self, subserver, stats):
        self.calls.append((subserver, stats))

    @classmethod
    def stats_conf(cls, name, conf):
        return ['ok']


class TestDaemonsSubserver(TestSubserver):

    _class = server.DaemonsSubserver

    def test_parse_conf_defaults(self):
        ss = TestSubserver.test_parse_conf_defaults(self)
        self.assertEquals(ss.daemons, [])
        self.assertEquals(ss.worker_count, 0)
        self.assertEquals(ss.worker_names, ['0'])

    def test_configure_daemons(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one two'
        confd.setdefault('one', {})['call'] = 'brim.daemon_sample.DaemonSample'
        confd.setdefault('two', {})['call'] = 'brim.daemon_sample.DaemonSample'
        conf = Conf(confd)
        ss._parse_conf(conf)
        self.assertEquals(len(ss.daemons), 2)
        self.assertEquals(ss.daemons[0][0], 'one')
        self.assertEquals(ss.daemons[1][0], 'two')
        self.assertEquals(ss.daemons[0][1].__name__, 'DaemonSample')
        self.assertEquals(ss.daemons[1][1].__name__, 'DaemonSample')
        self.assertEquals(ss.daemons[0][2],
                          ss.daemons[0][1].parse_conf('one', conf))
        self.assertEquals(ss.daemons[1][2],
                          ss.daemons[1][1].parse_conf('two', conf))

    def test_configure_daemons_conf_no_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['cll'] = 'brim.daemon_sample.DaemonSample'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
                          "Daemon [one] not configured with 'call' option.")

    def test_configure_daemons_conf_invalid_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = 'brim_daemon_sample_DaemonSample'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid call value "
            "'brim_daemon_sample_DaemonSample' for daemon [one].")

    def test_configure_daemons_no_load(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = 'brim.daemon_sample.aemon_sample'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Could not load class "
            "'brim.daemon_sample.aemon_sample' for daemon [one].")

    def test_configure_daemons_not_a_class(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = 'brim.server._send_pid_sig'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to instantiate "
            "'brim.server._send_pid_sig' for daemon [one]. Probably not a "
            "class.")

    def test_configure_daemons_invalid_init(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithInvalidInit'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to instantiate "
            "'brim.test.unit.test_server.DaemonWithInvalidInit' for daemon "
            "[one]. Incorrect number of args, 1, should be 3 (self, name, "
            "conf).")

    def test_configure_daemons_invalid_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithInvalidCall'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to use "
            "'brim.test.unit.test_server.DaemonWithInvalidCall' for daemon "
            "[one]. Incorrect number of __call__ args, 1, should be 3 (self, "
            "subserver, stats).")

    def test_configure_daemons_no_call(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithNoCall'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Would not be able to use "
            "'brim.test.unit.test_server.DaemonWithNoCall' for daemon "
            "[one]. Probably no __call__ method.")

    def test_configure_daemons_invalid_parse_conf1(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithInvalidParseConf1'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.DaemonWithInvalidParseConf1' for "
            "daemon [one]. Incorrect number of parse_conf args, 1, should be "
            "3 (cls, name, conf).")

    def test_configure_daemons_invalid_parse_conf2(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithInvalidParseConf2'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.DaemonWithInvalidParseConf2' for "
            "daemon [one]. parse_conf probably not a method.")

    def test_configure_daemons_no_parse_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithNoParseConf'
        conf = Conf(confd)
        ss._parse_conf(conf)
        self.assertEquals(ss.daemons[0][2], conf)

    def test_configure_daemons_with_parse_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithParseConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.daemons[0][2], {'ok': True})

    def test_configure_daemons_invalid_stats_conf1(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithInvalidStatsConf1'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.DaemonWithInvalidStatsConf1' for "
            "daemon [one]. Incorrect number of stats_conf args, 1, should be "
            "3 (cls, name, conf).")

    def test_configure_daemons_invalid_stats_conf2(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithInvalidStatsConf2'
        exc = None
        try:
            ss._parse_conf(Conf(confd))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot use "
            "'brim.test.unit.test_server.DaemonWithInvalidStatsConf2' for "
            "daemon [one]. stats_conf probably not a method.")

    def test_configure_daemons_no_stats_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithNoStatsConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.stats_conf.get('start_time'), 'worker')

    def test_configure_daemons_with_stats_conf(self):
        ss = self._class(FakeServer(), 'test')
        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = \
            'brim.test.unit.test_server.DaemonWithStatsConf'
        ss._parse_conf(Conf(confd))
        self.assertEquals(ss.stats_conf.get('start_time'), 'worker')
        self.assertEquals(ss.stats_conf.get('ok'), 'worker')

    def test_start(self, output=False):
        capture_exceptions_stdout_stderr_calls = []
        time_calls = []
        get_logger_calls = []
        fake_logger = FakeLogger()
        sustain_workers_calls = []

        def _capture_exceptions_stdout_stderr(*args, **kwargs):
            capture_exceptions_stdout_stderr_calls.append((args, kwargs))

        def _time(*args):
            time_calls.append(args)
            return len(time_calls)

        def _get_logger(*args):
            get_logger_calls.append(args)
            return fake_logger

        def _sustain_workers(*args, **kwargs):
            sustain_workers_calls.append((args, kwargs))

        confd = self._get_default_confd()
        confd.setdefault('test', {})['daemons'] = 'one'
        confd.setdefault('one', {})['call'] = 'brim.daemon_sample.DaemonSample'
        capture_exceptions_stdout_stderr_orig = \
            server.capture_exceptions_stdout_stderr
        time_orig = server.time
        get_logger_orig = server.get_logger
        sustain_workers_orig = server.sustain_workers
        try:
            server.capture_exceptions_stdout_stderr = \
                _capture_exceptions_stdout_stderr
            server.time = _time
            server.get_logger = _get_logger
            server.sustain_workers = _sustain_workers
            ss = TestSubserver.test_start(self, output=output, confd=confd)
        finally:
            server.capture_exceptions_stdout_stderr = \
                capture_exceptions_stdout_stderr_orig
            server.time = time_orig
            server.get_logger = get_logger_orig
            server.sustain_workers = sustain_workers_orig

        if output:
            self.assertEquals(capture_exceptions_stdout_stderr_calls, [])
        else:
            self.assertEquals(capture_exceptions_stdout_stderr_calls, [((),
                {'exceptions': ss._capture_exception,
                 'stdout_func': ss._capture_stdout,
                 'stderr_func': ss._capture_stderr})])
        self.assertEquals(time_calls, [()])
        self.assertEquals(get_logger_calls, [(ss.name, ss.log_name,
            ss.log_level, ss.log_facility, ss.server.no_daemon)])
        self.assertEquals(ss.worker_count, 1)
        self.assertEquals(sustain_workers_calls,
            [((ss.worker_count, ss._daemon), {'logger': fake_logger})])
        self.assertEquals(ss.worker_id, -1)
        self.assertEquals(ss.start_time, 1)
        self.assertEquals(ss.logger, fake_logger)
        self.assertEquals(fake_logger.error_calls, [])

    def test_start_with_output(self):
        self.test_start(output=True)

    def test_daemon(self, no_setproctitle=False):
        setproctitle_calls = []

        def _setproctitle(*args):
            setproctitle_calls.append(args)

        def _time():
            return 1

        def _sustain_workers(*args, **kwargs):
            pass

        setproctitle_orig = server.setproctitle
        time_orig = server.time
        sustain_workers_orig = server.sustain_workers
        try:
            server.setproctitle = None if no_setproctitle else _setproctitle
            server.time = _time
            server.sustain_workers = _sustain_workers
            ss = self._class(FakeServer(output=True), 'test')
            confd = self._get_default_confd()
            confd.setdefault('test', {})['daemons'] = 'one'
            confd.setdefault('one', {})['call'] = \
                'brim.test.unit.test_server.DaemonWithStatsConf'
            ss._parse_conf(Conf(confd))
            ss._privileged_start()
            bs = server._BucketStats(['0'], {'start_time': 'worker'})
            ss._start(bs)
            daemon = ss._daemon(0)
        finally:
            server.setproctitle = setproctitle_orig
            server.time = time_orig
            server.sustain_workers = sustain_workers_orig

        if no_setproctitle:
            self.assertEquals(setproctitle_calls, [])
        else:
            self.assertEquals(setproctitle_calls, [('one:test:brimd',)])
        self.assertEquals(ss.worker_id, 0)
        self.assertEquals(ss.bucket_stats.get(ss.worker_id, 'start_time'), 1)
        self.assertEquals(ss.daemons[0][0], 'one')
        self.assertEquals(ss.daemons[0][1].__name__, 'DaemonWithStatsConf')
        self.assertEquals(ss.daemons[0][2].store,
            {'test': {'daemons': 'one'},
            'one': {'call': 'brim.test.unit.test_server.DaemonWithStatsConf'}})
        self.assertEquals(len(daemon.calls), 1)
        self.assertEquals(len(daemon.calls[0]), 2)
        self.assertEquals(daemon.calls[0][0], ss)
        self.assertEquals(daemon.calls[0][1].bucket_stats, ss.bucket_stats)

    def test_daemon_no_setproctitle(self):
        self.test_daemon(no_setproctitle=True)

    def test_capture_exception(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_exception(*exc_info())
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls,
                          [("UNCAUGHT EXCEPTION: did:123 None ['None']",)])
        self.assertEquals(ss.logger.exception_calls, [])

        ss.logger = FakeLogger()
        try:
            raise Exception('test')
        except Exception:
            ss._capture_exception(*exc_info())
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(len(ss.logger.error_calls), 1)
        self.assertEquals(len(ss.logger.error_calls[0]), 1)
        e = ss.logger.error_calls[0][0]
        self.assertTrue(e.startswith("UNCAUGHT EXCEPTION: did:123 Exception: "
            "test ['Traceback (most recent call last):', '  File "))
        self.assertTrue(e.endswith('\', "    raise Exception(\'test\')", '
            '\'Exception: test\']'))
        self.assertEquals(ss.logger.exception_calls, [])

    def test_capture_stdout(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_stdout('one\ntwo three\nfour\n')
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [('STDOUT: did:123 one',),
            ('STDOUT: did:123 two three',), ('STDOUT: did:123 four',)])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls, [])
        self.assertEquals(ss.logger.exception_calls, [])

    def test_capture_stderr(self):
        ss = self._class(FakeServer(output=True), 'test')
        ss.logger = FakeLogger()
        ss.worker_id = 123
        ss._capture_stderr('one\ntwo three\nfour\n')
        self.assertEquals(ss.logger.debug_calls, [])
        self.assertEquals(ss.logger.info_calls, [])
        self.assertEquals(ss.logger.notice_calls, [])
        self.assertEquals(ss.logger.error_calls, [('STDERR: did:123 one',),
            ('STDERR: did:123 two three',), ('STDERR: did:123 four',)])
        self.assertEquals(ss.logger.exception_calls, [])


class TestServer(TestCase):

    def setUp(self):
        self.orig_read_conf = server.read_conf
        self.orig_fork = server.fork
        self.orig_sleep = server.sleep
        self.orig_send_pid_sig = server._send_pid_sig
        self.orig_droppriv = server.droppriv
        self.orig_get_logger = server.get_logger
        self.orig_capture_exceptions_stdout_stderr = \
            server.capture_exceptions_stdout_stderr
        self.read_conf_calls = []
        self.conf = Conf({})
        self.fork_calls = []
        self.fork_retval = [12345]
        self.sleep_calls = []
        self.send_pid_sig_calls = []
        self.send_pid_sig_retval = [True, 12345]
        self.droppriv_calls = []
        self.get_logger_calls = []
        self.capture_calls = []

        def _read_conf(*args):
            self.read_conf_calls.append(args)
            return self.conf

        def _fork(*args):
            self.fork_calls.append(args)
            if len(self.fork_retval) > 1:
                return self.fork_retval.pop(0)
            return self.fork_retval[0]

        def _sleep(*args):
            self.sleep_calls.append(args)

        def _send_pid_sig(*args, **kwargs):
            self.send_pid_sig_calls.append((args, kwargs))
            return self.send_pid_sig_retval

        def _droppriv(*args):
            self.droppriv_calls.append(args)

        def _get_logger(*args):
            self.get_logger_calls.append(args)
            return FakeLogger()

        def _capture_exceptions_stdout_stderr(*args, **kwargs):
            self.capture_calls.append((args, kwargs))

        server.read_conf = _read_conf
        server.fork = _fork
        server.sleep = _sleep
        server._send_pid_sig = _send_pid_sig
        server.droppriv = _droppriv
        server.get_logger = _get_logger
        server.capture_exceptions_stdout_stderr = \
            _capture_exceptions_stdout_stderr
        self.stdin = StringIO()
        self.stdout = StringIO()
        self.stderr = StringIO()
        self.serv = server.Server([], self.stdin, self.stdout, self.stderr)

    def tearDown(self):
        server.read_conf = self.orig_read_conf
        server.fork = self.orig_fork
        server.sleep = self.orig_sleep
        server._send_pid_sig = self.orig_send_pid_sig
        server.droppriv = self.orig_droppriv
        server.get_logger = self.orig_get_logger
        server.capture_exceptions_stdout_stderr = \
            self.orig_capture_exceptions_stdout_stderr

    def test_uses_standard_items_by_default(self):
        serv = server.Server()
        self.assertEquals(serv.args, server.sys_argv[1:])
        self.assertEquals(serv.stdin, server.sys_stdin)
        self.assertEquals(serv.stdout, server.sys_stdout)
        self.assertEquals(serv.stderr, server.sys_stderr)

    def test_main(self):
        self.conf = Conf({'brim': {'port': '0'}, 'wsgi': {}})
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        server_calls = []

        def _server(*args, **kwargs):
            server_calls.append((args, kwargs))

        orig_wsgi_server = server.wsgi.server
        try:
            server.wsgi.server = _server
            self.assertEquals(self.serv.main(), 0)
        finally:
            server.wsgi.server = orig_wsgi_server

        self.assertEquals(len(server_calls), 1)

    def test_args_exception(self):
        self.serv.args = [123]
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(),
                          "'int' object is unsubscriptable\n")

    def test_args_help1(self):
        self.serv.args = ['-?']
        try:
            self.assertEquals(self.serv.main(), 0)
        except SystemExit:
            pass
        self.assertTrue('Usage: ' in self.stdout.getvalue())
        self.assertTrue("Command (defaults to 'no-daemon'):" in
                        self.stdout.getvalue())
        self.assertTrue('Options:' in self.stdout.getvalue())
        self.assertEquals(self.stderr.getvalue(), '')

    def test_args_help2(self):
        self.serv.args = ['-h']
        try:
            self.assertEquals(self.serv.main(), 0)
        except SystemExit:
            pass
        self.assertTrue('Usage: ' in self.stdout.getvalue())
        self.assertTrue("Command (defaults to 'no-daemon'):" in
                        self.stdout.getvalue())
        self.assertTrue('Options:' in self.stdout.getvalue())
        self.assertEquals(self.stderr.getvalue(), '')

    def test_args_help3(self):
        self.serv.args = ['--help']
        try:
            self.assertEquals(self.serv.main(), 0)
        except SystemExit:
            pass
        self.assertTrue('Usage: ' in self.stdout.getvalue())
        self.assertTrue("Command (defaults to 'no-daemon'):" in
                        self.stdout.getvalue())
        self.assertTrue('Options:' in self.stdout.getvalue())
        self.assertEquals(self.stderr.getvalue(), '')

    def test_args_default_conf(self):
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.read_conf_calls, [(server.DEFAULT_CONF_FILES,)])

    def test_args_override_conf1(self):
        self.serv.args = ['-c', 'one.conf']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.read_conf_calls, [(['one.conf'],)])
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), 'No configuration found.\n')

    def test_args_override_conf2(self):
        self.serv.args = ['-c', 'one.conf', '--conf', 'two.conf']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.read_conf_calls, [(['one.conf', 'two.conf'],)])
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), 'No configuration found.\n')

    def test_args_default_pid_file(self):
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.serv.pid_file, '/var/run/brimd.pid')

    def test_args_override_pid_file1(self):
        self.serv.args = ['-p', 'pidfile']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.serv.pid_file, 'pidfile')

    def test_args_override_pid_file2(self):
        self.serv.args = ['--pid-file', 'pidfile']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.serv.pid_file, 'pidfile')

    def test_args_default_nodaemon_output(self):
        self.assertEquals(self.serv.main(), 1)
        self.assertTrue(self.serv.output)

    def test_args_default_start_output(self):
        self.serv.args = ['start']
        self.send_pid_sig_retval[0] = False
        self.assertEquals(self.serv.main(), 1)
        self.assertFalse(self.serv.output)

    def test_args_override_output1(self):
        self.serv.args = ['start', '-o']
        self.send_pid_sig_retval[0] = False
        self.assertEquals(self.serv.main(), 1)
        self.assertTrue(self.serv.output)

    def test_args_override_output2(self):
        self.serv.args = ['start', '--output']
        self.send_pid_sig_retval[0] = False
        self.assertEquals(self.serv.main(), 1)
        self.assertTrue(self.serv.output)

    def test_version(self):
        self.serv.args = ['--version']
        self.assertEquals(self.serv.main(), 0)
        self.assertEquals(self.stdout.getvalue(),
                          'Brim.Net Core Server %s\n' % version)
        self.assertEquals(self.stderr.getvalue(), '')

    def test_parser_error(self):
        self.serv.args = ['--invalid']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(),
                          'no such option: --invalid\n')

    def test_too_many_commands(self):
        self.serv.args = ['one', 'two']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(),
                          'Too many commands given; only one allowed.\n')

    def test_default_command_no_daemon1(self):
        self.assertEquals(self.serv.main(), 1)
        self.assertTrue(self.serv.no_daemon)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), 'No configuration found.\n')

    def test_default_command_no_daemon2(self):
        self.serv.args = ['start']
        self.send_pid_sig_retval[0] = False
        self.assertEquals(self.serv.main(), 1)
        self.assertFalse(self.serv.no_daemon)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), 'No configuration found.\n')

    def test_start_already_running(self):
        self.serv.args = ['start']
        self.assertEquals(self.serv.main(), 0)
        self.assertEquals(self.stdout.getvalue(), '12345 already running\n')
        self.assertEquals(self.stderr.getvalue(), '')

    def test_start_no_conf(self):
        self.serv.args = ['start']
        self.send_pid_sig_retval[0] = False
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), 'No configuration found.\n')

    def test_start_has_conf(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['start']
        self.send_pid_sig_retval[0] = False
        self.assertEquals(self.serv._parse_args(), self.conf)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), '')

    def test_restart_no_conf(self):
        self.serv.args = ['restart']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), 'No configuration found.\n')

    def test_restart_has_conf(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['restart']
        self.assertEquals(self.serv._parse_args(), self.conf)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.fork_calls, [()])

    def test_restart_has_conf_fork_side(self):
        self.fork_retval[0] = 0
        self.conf.files = ['ok.conf']
        self.serv.args = ['restart']
        self.assertEquals(self.serv.main(), 0)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.fork_calls, [()])
        self.assertEquals(self.send_pid_sig_calls,
            [((self.serv.pid_file, 0), {}),
             ((self.serv.pid_file, server.SIGHUP),
              {'expect_exit': True, 'pid_override': 12345})])

    def test_reload_no_conf(self):
        self.serv.args = ['reload']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), 'No configuration found.\n')

    def test_reload_has_conf(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['reload']
        self.assertEquals(self.serv._parse_args(), self.conf)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.fork_calls, [()])

    def test_reload_has_conf_fork_side(self):
        self.fork_retval[0] = 0
        self.conf.files = ['ok.conf']
        self.serv.args = ['reload']
        self.assertEquals(self.serv.main(), 0)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.fork_calls, [()])
        self.assertEquals(self.send_pid_sig_calls,
            [((self.serv.pid_file, 0), {}),
             ((self.serv.pid_file, server.SIGHUP),
              {'expect_exit': True, 'pid_override': 12345})])

    def test_force_reload_no_conf(self):
        self.serv.args = ['force-reload']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), 'No configuration found.\n')

    def test_force_reload_has_conf(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['force-reload']
        self.assertEquals(self.serv._parse_args(), self.conf)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.fork_calls, [()])

    def test_force_reload_has_conf_fork_side(self):
        self.fork_retval[0] = 0
        self.conf.files = ['ok.conf']
        self.serv.args = ['force-reload']
        self.assertEquals(self.serv.main(), 0)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.fork_calls, [()])
        self.assertEquals(self.send_pid_sig_calls,
            [((self.serv.pid_file, 0), {}),
             ((self.serv.pid_file, server.SIGHUP),
              {'expect_exit': True, 'pid_override': 12345})])

    def test_shutdown(self):
        self.serv.args = ['shutdown']
        self.assertEquals(self.serv.main(), 0)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.send_pid_sig_calls,
            [((self.serv.pid_file, server.SIGHUP), {'expect_exit': True})])

    def test_stop(self):
        self.serv.args = ['stop']
        self.assertEquals(self.serv.main(), 0)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.send_pid_sig_calls,
            [((self.serv.pid_file, server.SIGTERM), {'expect_exit': True})])

    def test_status_running(self):
        self.serv.args = ['status']
        self.assertEquals(self.serv.main(), 0)
        self.assertEquals(self.stdout.getvalue(), '12345 is running\n')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.send_pid_sig_calls,
                          [((self.serv.pid_file, 0), {})])

    def test_status_not_running(self):
        self.send_pid_sig_retval[0] = False
        self.serv.args = ['status']
        self.assertEquals(self.serv.main(), 0)
        self.assertEquals(self.stdout.getvalue(), '12345 is not running\n')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.send_pid_sig_calls,
                          [((self.serv.pid_file, 0), {})])

    def test_status_not_running_no_pid(self):
        self.send_pid_sig_retval[0] = False
        self.send_pid_sig_retval[1] = 0
        self.serv.args = ['status']
        self.assertEquals(self.serv.main(), 0)
        self.assertEquals(self.stdout.getvalue(), 'not running\n')
        self.assertEquals(self.stderr.getvalue(), '')
        self.assertEquals(self.send_pid_sig_calls,
                          [((self.serv.pid_file, 0), {})])

    def test_no_daemon_no_conf(self):
        self.serv.args = ['no-daemon']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), 'No configuration found.\n')

    def test_no_daemon_has_conf(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        self.assertEquals(self.serv._parse_args(), self.conf)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(), '')

    def test_unknown_command(self):
        self.serv.args = ['unknown']
        self.assertEquals(self.serv.main(), 1)
        self.assertEquals(self.stdout.getvalue(), '')
        self.assertEquals(self.stderr.getvalue(),
                          "Unknown command 'unknown'.\n")

    def test_parse_conf_default(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['start']
        self.serv._parse_args()
        self.serv._parse_conf(Conf({
            'wsgi': {'port': '1234'},
            'wsgi2': {},
            'tcp': {'call': 'brim.test.unit.test_server.TCPWithStatsConf'},
            'tcp2': {'call': 'brim.test.unit.test_server.TCPWithStatsConf'},
            'udp': {'call': 'brim.test.unit.test_server.UDPWithStatsConf'},
            'udp2': {'call': 'brim.test.unit.test_server.UDPWithStatsConf'},
            'daemons': {}}))
        self.assertEquals(self.serv.user, None)
        self.assertEquals(self.serv.group, None)
        self.assertEquals(self.serv.umask, 0022)
        self.assertEquals(self.serv.log_name, 'brim')
        self.assertEquals(self.serv.log_level, 'INFO')
        self.assertEquals(self.serv.log_facility, 'LOG_LOCAL0')
        self.assertEquals(sorted(s.name for s in self.serv.subservers),
            ['daemons', 'tcp', 'tcp2', 'udp', 'udp2', 'wsgi', 'wsgi2'])
        # Just verifies subserver._parse_conf was called.
        wsgi = [s for s in self.serv.subservers if s.name == 'wsgi'][0]
        self.assertEquals(wsgi.port, 1234)

    def test_parse_conf_sets_error_handler(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        self.serv._parse_args()
        conf = Conf({'brim': {'test': 'abc'}})
        # Asserts conf.error is still the default behavior of SystemExit.
        exc = None
        try:
            conf.get_int('brim', 'test', 0)
        except SystemExit, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] test of 'abc' "
                                    "cannot be converted to int.")
        self.serv._parse_conf(conf)
        # Asserts conf.error is now the new behavior of just raising Exception.
        exc = None
        try:
            conf.get_int('brim', 'test', 0)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Configuration value [brim] test of 'abc' "
                                    "cannot be converted to int.")

    def test_parse_conf_user(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        self.serv._parse_args()
        self.serv._parse_conf(Conf({'brim': {'user': 'name'}}))
        self.assertEquals(self.serv.user, 'name')

    def test_parse_conf_group(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        self.serv._parse_args()
        self.serv._parse_conf(Conf({'brim': {'group': 'name'}}))
        self.assertEquals(self.serv.group, 'name')

    def test_parse_conf_umask(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        self.serv._parse_args()
        self.serv._parse_conf(Conf({'brim': {'umask': '0777'}}))
        self.assertEquals(self.serv.umask, 0777)
        exc = None
        try:
            self.serv._parse_conf(Conf({'brim': {'umask': 'abc'}}))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid umask value 'abc'.")
        exc = None
        try:
            self.serv._parse_conf(Conf({'brim': {'umask': '99'}}))
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Invalid umask value '99'.")

    def test_parse_conf_log_name(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        self.serv._parse_args()
        self.serv._parse_conf(Conf({'brim': {'log_name': 'name'}}))
        self.assertEquals(self.serv.log_name, 'name')

    def test_parse_conf_log_level(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        self.serv._parse_args()
        self.serv._parse_conf(Conf({'brim': {'log_level': 'DEBUG'}}))
        self.assertEquals(self.serv.log_level, 'DEBUG')
        exc = None
        try:
            self.serv._parse_conf(Conf({'brim': {'log_level': 'invalid'}}))
        except Exception, err:
            exc = err
        self.assertEquals(str(err), "Invalid [brim] log_level 'INVALID'.")

    def test_parse_conf_log_facility(self):
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        self.serv._parse_args()
        self.serv._parse_conf(
            Conf({'brim': {'log_facility': 'LOG_LOCAL1'}}))
        self.assertEquals(self.serv.log_facility, 'LOG_LOCAL1')
        self.serv._parse_conf(Conf({'brim': {'log_facility': 'LOCAL2'}}))
        self.assertEquals(self.serv.log_facility, 'LOG_LOCAL2')
        exc = None
        try:
            self.serv._parse_conf(
                Conf({'brim': {'log_facility': 'invalid'}}))
        except Exception, err:
            exc = err
        self.assertEquals(str(err),
                          "Invalid [brim] log_facility 'LOG_INVALID'.")

    def test_start(self):
        self.conf = Conf({'brim': {'port': '0'}, 'wsgi': {}})
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        self.serv._parse_args()
        self.serv._parse_conf(self.conf)
        subserv = self.serv.subservers[0]
        subserv._parse_conf(self.conf)
        sustain_workers_calls = []

        def _sustain_workers(*args, **kwargs):
            sustain_workers_calls.append((args, kwargs))

        orig_sustain_workers = server.sustain_workers
        try:
            server.sustain_workers = _sustain_workers
            self.serv._start()
        finally:
            server.sustain_workers = orig_sustain_workers
        # Since we're in no-daemon, Server didn't call sustain_workers, but the
        # wsgi subserver did.
        self.assertEquals(sustain_workers_calls,
            [((0, subserv._wsgi_worker), {'logger': subserv.logger})])

    def test_start_no_subservers(self):
        self.conf = Conf({'brim': {'port': '0'}})
        self.conf.files = ['ok.conf']
        self.serv.args = ['no-daemon']
        self.serv._parse_args()
        self.serv._parse_conf(self.conf)
        sustain_workers_calls = []

        def _sustain_workers(*args, **kwargs):
            sustain_workers_calls.append((args, kwargs))

        orig_sustain_workers = server.sustain_workers
        exc = None
        try:
            server.sustain_workers = _sustain_workers
            self.serv._start()
        except Exception, err:
            exc = err
        finally:
            server.sustain_workers = orig_sustain_workers
        self.assertEquals(str(exc), 'No subservers configured.')
        self.assertEquals(sustain_workers_calls, [])

    def test_start_daemoned_parent_side(self):
        self.conf = Conf({'brim': {'port': '0'}, 'wsgi': {}})
        self.conf.files = ['ok.conf']
        self.serv.args = ['start']
        self.serv._parse_args()
        self.serv._parse_conf(self.conf)
        subserv = self.serv.subservers[0]
        subserv._parse_conf(self.conf)
        sustain_workers_calls = []
        open_retval = [StringIO()]
        open_calls = []

        def _sustain_workers(*args, **kwargs):
            sustain_workers_calls.append((args, kwargs))

        @contextmanager
        def _open(*args):
            open_calls.append(args)
            yield open_retval[0]

        orig_sustain_workers = server.sustain_workers
        try:
            server.sustain_workers = _sustain_workers
            server.open = _open
            self.serv._start()
        finally:
            server.sustain_workers = orig_sustain_workers
            del server.open
        self.assertEquals(sustain_workers_calls, [])
        self.assertEquals(open_calls, [('/var/run/brimd.pid', 'w')])
        self.assertEquals(open_retval[0].getvalue(), '12345\n')

    def test_start_daemoned_child_side(self):
        self.conf = Conf({'brim': {'port': '0'}, 'wsgi': {}})
        self.conf.files = ['ok.conf']
        self.serv.args = ['start']
        self.serv._parse_args()
        self.serv._parse_conf(self.conf)
        subserv = self.serv.subservers[0]
        subserv._parse_conf(self.conf)
        sustain_workers_calls = []
        self.fork_retval[0] = 0

        def _sustain_workers(*args, **kwargs):
            sustain_workers_calls.append((args, kwargs))

        orig_sustain_workers = server.sustain_workers
        try:
            server.sustain_workers = _sustain_workers
            self.serv._start()
        finally:
            server.sustain_workers = orig_sustain_workers
        self.assertEquals(sustain_workers_calls,
            [((1, self.serv._start_subserver), {'logger': self.serv.logger})])
        self.assertEquals(self.capture_calls, [
            ((), {'exceptions': self.serv._capture_exception,
                  'stdout_func': self.serv._capture_stdout,
                  'stderr_func': self.serv._capture_stderr})])

    def test_start_daemoned_child_side_console_mode(self):
        self.conf = Conf({'brim': {'port': '0'}, 'wsgi': {}})
        self.conf.files = ['ok.conf']
        self.serv.args = ['-o', 'start']
        self.serv._parse_args()
        self.serv._parse_conf(self.conf)
        subserv = self.serv.subservers[0]
        subserv._parse_conf(self.conf)
        sustain_workers_calls = []
        self.fork_retval[0] = 0

        def _sustain_workers(*args, **kwargs):
            sustain_workers_calls.append((args, kwargs))

        orig_sustain_workers = server.sustain_workers
        try:
            server.sustain_workers = _sustain_workers
            self.serv._start()
        finally:
            server.sustain_workers = orig_sustain_workers
        self.assertEquals(sustain_workers_calls,
            [((1, self.serv._start_subserver), {'logger': self.serv.logger})])
        self.assertEquals(self.capture_calls, [])

    def test_start_subserver(self, no_setproctitle=False):
        self.conf = Conf({'brim': {'port': '0'}, 'wsgi': {}})
        self.conf.files = ['ok.conf']
        self.serv.args = ['start']
        self.serv._parse_args()
        self.serv._parse_conf(self.conf)
        subserv = self.serv.subservers[0]
        subserv._parse_conf(self.conf)
        sustain_workers_calls = []
        self.fork_retval[0] = 0

        def _sustain_workers(*args, **kwargs):
            sustain_workers_calls.append((args, kwargs))

        orig_sustain_workers = server.sustain_workers
        try:
            server.sustain_workers = _sustain_workers
            self.serv._start()
        finally:
            server.sustain_workers = orig_sustain_workers
        self.assertEquals(sustain_workers_calls,
            [((1, self.serv._start_subserver), {'logger': self.serv.logger})])
        self.assertEquals(self.capture_calls, [
            ((), {'exceptions': self.serv._capture_exception,
                  'stdout_func': self.serv._capture_stdout,
                  'stderr_func': self.serv._capture_stderr})])

        setproctitle_calls = []
        start_calls = []

        def _setproctitle(*args):
            setproctitle_calls.append(args)

        def _start(*args):
            start_calls.append(args)

        setproctitle_orig = server.setproctitle
        try:
            server.setproctitle = None if no_setproctitle else _setproctitle
            subserv._start = _start
            self.serv._start_subserver(0)
        finally:
            server.setproctitle = setproctitle_orig
        if no_setproctitle:
            self.assertEquals(setproctitle_calls, [])
        else:
            self.assertEquals(setproctitle_calls, [('wsgi:brimd',)])
        self.assertEquals(start_calls, [(self.serv.bucket_stats[0],)])

    def test_start_subserver_no_setproctitle(self):
        self.test_start_subserver(no_setproctitle=True)

    def test_capture_exception(self):
        self.serv.logger = FakeLogger()
        self.serv._capture_exception()
        self.assertEquals(self.serv.logger.error_calls,
                          [("UNCAUGHT EXCEPTION: main None ['None']",)])

        self.serv.logger = FakeLogger()
        try:
            raise Exception('testing')
        except Exception:
            self.serv._capture_exception(*exc_info())
        self.assertEquals(len(self.serv.logger.error_calls), 1)
        self.assertEquals(len(self.serv.logger.error_calls[0]), 1)
        self.assertTrue(self.serv.logger.error_calls[0][0].startswith(
            'UNCAUGHT EXCEPTION: main Exception: testing [\'Traceback '
            '(most recent call last):\''))
        self.assertTrue(self.serv.logger.error_calls[0][0].endswith(
            '    raise Exception(\'testing\')", \'Exception: testing\']'))

    def test_capture_stdout(self):
        self.serv.logger = FakeLogger()
        self.serv._capture_stdout('one\ntwo\nthree\n')
        self.assertEquals(self.serv.logger.info_calls,
            [('STDOUT: main one',), ('STDOUT: main two',),
             ('STDOUT: main three',)])

        self.serv.logger = FakeLogger()
        self.serv._capture_stdout('one\ntwo\nthree\n')
        self.assertEquals(self.serv.logger.info_calls,
            [('STDOUT: main one',), ('STDOUT: main two',),
             ('STDOUT: main three',)])

    def test_capture_stderr(self):
        self.serv.logger = FakeLogger()
        self.serv._capture_stderr('one\ntwo\nthree\n')
        self.assertEquals(self.serv.logger.error_calls,
            [('STDERR: main one',), ('STDERR: main two',),
             ('STDERR: main three',)])

        self.serv.logger = FakeLogger()
        self.serv._capture_stderr('one\ntwo\nthree\n')
        self.assertEquals(self.serv.logger.error_calls,
            [('STDERR: main one',), ('STDERR: main two',),
             ('STDERR: main three',)])


if __name__ == '__main__':
    main()
