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

import socket
import ssl
import time
from errno import EADDRINUSE, EPERM
from os import devnull
from StringIO import StringIO
from unittest import main, TestCase
from nose import SkipTest

from brim import service


class Test_capture_exceptions_stdout_stderr(TestCase):

    def setUp(self):
        self.orig_sys = service.sys
        self.orig_dup2 = service.dup2
        self.dup2calls = []

        def _dup2(*args):
            self.dup2calls.append(args)

        service.sys = self
        service.dup2 = _dup2

    def tearDown(self):
        service.sys = self.orig_sys
        service.dup2 = self.orig_dup2

    def test_calls_flush_dup2_on_standard_io(self):

        class FakeFile(object):

            def __init__(self, fileno):
                self._fileno = fileno
                self._flush_calls = 0

            def fileno(self):
                return self._fileno

            def flush(self):
                self._flush_calls += 1

        self.stdout = stdout = FakeFile(456)
        self.stderr = stderr = FakeFile(789)
        service.capture_exceptions_stdout_stderr()
        self.assertEquals(set([b for a, b in self.dup2calls]),
                          set([stdout.fileno(), stderr.fileno()]))
        self.assertEquals(stdout._flush_calls, 1)
        self.assertEquals(stderr._flush_calls, 1)

    def test_does_not_call_dup2_on_things_not_understood(self):
        self.stdout = 'stdout'
        self.stderr = 'stderr'
        service.capture_exceptions_stdout_stderr()
        self.assertEquals(len(self.dup2calls), 0)

    def test_ignores_dup2_exceptions(self):
        self.stdout = open(devnull, 'wb')
        self.stderr = open(devnull, 'wb')

        def _dup2(*args):
            raise OSError()

        orig_dup2 = service.dup2
        try:
            service.dup2 = _dup2
            service.capture_exceptions_stdout_stderr()
        finally:
            service.dup2 = orig_dup2

    def test_output_is_redirected(self):
        self.stdout = 'stdout'
        self.stderr = 'stderr'
        service.capture_exceptions_stdout_stderr()
        # These would raise exceptions if not replaced by the above call.
        print >>self.stdout, 'test stdout'
        print >>self.stderr, 'test stderr'

    def test_excepthook_is_set(self):
        self.excepthook = 'excepthook'
        self.stdout = 'stdout'
        self.stderr = 'stderr'
        service.capture_exceptions_stdout_stderr()
        self.assertNotEquals(self.excepthook, 'excepthook')

    def test_excepthook_calls_us(self):
        self.stdout = 'stdout'
        self.stderr = 'stderr'
        calls = []

        def _exc(*args):
            calls.append(args)

        service.capture_exceptions_stdout_stderr(_exc)
        self.assertEquals(len(calls), 0)
        self.excepthook(1, 2, 3)
        self.assertEquals(calls, [(1, 2, 3)])

    def test_stdout_calls_us(self):
        self.stdout = 'stdout'
        self.stderr = 'stderr'
        calls = []

        def _stdout(*args):
            calls.append(args)

        service.capture_exceptions_stdout_stderr(stdout_func=_stdout)
        self.assertEquals(len(calls), 0)
        print >>self.stdout, 'test'
        self.assertEquals(calls, [('test\n',)])

    def test_stderr_calls_us(self):
        self.stdout = 'stdout'
        self.stderr = 'stderr'
        calls = []

        def _stderr(*args):
            calls.append(args)

        service.capture_exceptions_stdout_stderr(stderr_func=_stderr)
        self.assertEquals(len(calls), 0)
        print >>self.stderr, 'test'
        self.assertEquals(calls, [('test\n',)])

    def test_combine_writes(self):
        self.stdout = 'stdout'
        self.stderr = 'stderr'
        calls = []

        def _stdout(*args):
            calls.append(args)

        service.capture_exceptions_stdout_stderr(stdout_func=_stdout)
        self.assertEquals(len(calls), 0)
        print >>self.stdout, 'test',
        self.assertEquals(calls, [])
        print >>self.stdout, 'and more'
        self.assertEquals(calls, [('test and more\n',)])

    def test_combine_writes_unless_flush(self):
        self.stdout = 'stdout'
        self.stderr = 'stderr'
        calls = []

        def _stdout(*args):
            calls.append(args)

        service.capture_exceptions_stdout_stderr(stdout_func=_stdout)
        self.assertEquals(len(calls), 0)
        print >>self.stdout, 'test',
        self.assertEquals(calls, [])
        self.stdout.flush()
        self.assertEquals(calls, [('test',)])
        print >>self.stdout, 'and more'
        self.assertEquals(calls, [('test',), (' and more\n',)])

    def test_close_just_flushes(self):
        self.stdout = 'stdout'
        self.stderr = 'stderr'
        calls = []

        def _stdout(*args):
            calls.append(args)

        service.capture_exceptions_stdout_stderr(stdout_func=_stdout)
        self.assertEquals(len(calls), 0)
        print >>self.stdout, 'test',
        self.assertEquals(calls, [])
        self.stdout.close()
        self.assertEquals(calls, [('test',)])
        print >>self.stdout, 'and more'
        self.assertEquals(calls, [('test',), (' and more\n',)])

    def test_writelines(self):
        self.stdout = 'stdout'
        self.stderr = 'stderr'
        calls = []

        def _stdout(*args):
            calls.append(args)

        service.capture_exceptions_stdout_stderr(stdout_func=_stdout)
        self.assertEquals(len(calls), 0)
        self.stdout.writelines(['abc\n', 'def', 'ghi\n', 'jkl'])
        self.assertEquals(calls, [('abc\ndefghi\n',)])
        self.stdout.flush()
        self.assertEquals(calls, [('abc\ndefghi\n',), ('jkl',)])


class Test_droppriv(TestCase):

    def setUp(self):
        self.orig_geteuid = service.geteuid
        self.orig_getegid = service.getegid
        self.orig_getpwnam = service.getpwnam
        self.orig_getgrnam = service.getgrnam
        self.orig_setuid = service.setuid
        self.orig_setgid = service.setgid
        self.orig_os_umask = service.os_umask
        self.orig_setsid = service.setsid
        self.orig_chdir = service.chdir
        self.orig_setgroups = service.setgroups

        class PWNam(object):

            def __init__(self, uid, gid):
                self.pw_uid = uid
                self.pw_gid = gid

        class GrNam(object):

            def __init__(self, gid):
                self.gr_gid = gid

        self.euid = 1
        self.egid = 2
        self.pwnam = {'user': PWNam(self.euid, self.egid)}
        self.grnam = {'group': GrNam(self.egid)}
        self.setuid_calls = []
        self.setgid_calls = []
        self.os_umask_calls = []
        self.setsid_calls = []
        self.chdir_calls = []
        self.setgroups_calls = []
        service.geteuid = lambda: self.euid
        service.getegid = lambda: self.egid
        service.getpwnam = lambda u: self.pwnam[u]
        service.getgrnam = lambda g: self.grnam[g]
        service.setuid = lambda *a: self.setuid_calls.append(a)
        service.setgid = lambda *a: self.setgid_calls.append(a)
        service.os_umask = lambda *a: self.os_umask_calls.append(a)
        service.setsid = lambda *a: self.setsid_calls.append(a)
        service.chdir = lambda *a: self.chdir_calls.append(a)
        service.setgroups = lambda *a: self.setgroups_calls.append(a)

    def tearDown(self):
        service.geteuid = self.orig_geteuid
        service.getegid = self.orig_getegid
        service.getpwnam = self.orig_getpwnam
        service.getgrnam = self.orig_getgrnam
        service.setuid = self.orig_setuid
        service.setgid = self.orig_setgid
        service.os_umask = self.orig_os_umask
        service.setsid = self.orig_setsid
        service.chdir = self.orig_chdir
        service.setgroups = self.orig_setgroups

    def test_droppriv_to_same_uid_gid(self):
        service.droppriv('user')
        self.assertEquals(self.setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [(1,)])
        self.assertEquals(self.setgid_calls, [(2,)])
        self.assertEquals(self.os_umask_calls, [(0022,)])
        self.assertEquals(self.setsid_calls, [()])
        self.assertEquals(self.chdir_calls, [('/',)])

    def test_droppriv_to_different_uid_default_gid(self):
        self.pwnam['user'].pw_uid = 10
        self.pwnam['user'].pw_gid = 20
        self.grnam['group'].gr_gid = 30
        service.droppriv('user')
        self.assertEquals(self.setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [(10,)])
        self.assertEquals(self.setgid_calls, [(20,)])
        self.assertEquals(self.os_umask_calls, [(0022,)])
        self.assertEquals(self.setsid_calls, [()])
        self.assertEquals(self.chdir_calls, [('/',)])

    def test_droppriv_to_different_uid_gid(self):
        self.pwnam['user'].pw_uid = 10
        self.pwnam['user'].pw_gid = 20
        self.grnam['group'].gr_gid = 30
        service.droppriv('user', 'group')
        self.assertEquals(self.setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [(10,)])
        self.assertEquals(self.setgid_calls, [(30,)])
        self.assertEquals(self.os_umask_calls, [(0022,)])
        self.assertEquals(self.setsid_calls, [()])
        self.assertEquals(self.chdir_calls, [('/',)])

    def test_droppriv_umask(self):
        service.droppriv('user', umask=0123)
        self.assertEquals(self.setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [(1,)])
        self.assertEquals(self.setgid_calls, [(2,)])
        self.assertEquals(self.os_umask_calls, [(0123,)])
        self.assertEquals(self.setsid_calls, [()])
        self.assertEquals(self.chdir_calls, [('/',)])

    def test_droppriv_unknown_user(self):
        exc = None
        try:
            service.droppriv('unknown')
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Cannot switch to unknown user 'unknown'.")
        self.assertEquals(self.setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [])
        self.assertEquals(self.setgid_calls, [])
        self.assertEquals(self.os_umask_calls, [])
        self.assertEquals(self.setsid_calls, [])
        self.assertEquals(self.chdir_calls, [])

    def test_droppriv_unknown_group(self):
        exc = None
        try:
            service.droppriv('user', 'unknown')
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
                          "Cannot switch to unknown group 'unknown'.")
        self.assertEquals(self.setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [])
        self.assertEquals(self.setgid_calls, [])
        self.assertEquals(self.os_umask_calls, [])
        self.assertEquals(self.setsid_calls, [])
        self.assertEquals(self.chdir_calls, [])

    def test_setuid_failure(self):

        def _setuid(*args):
            raise OSError()

        exc = None
        orig_setuid = service.setuid
        try:
            service.setuid = _setuid
            service.droppriv('user')
        except Exception, err:
            exc = err
        finally:
            service.setuid = orig_setuid
        self.assertEquals(str(exc),
                          "Permission denied when switching to user 'user'.")
        self.assertEquals(self.setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [])
        # This also asserts setgid is called before setuid.
        self.assertEquals(self.setgid_calls, [(2,)])
        self.assertEquals(self.os_umask_calls, [])
        self.assertEquals(self.setsid_calls, [])
        self.assertEquals(self.chdir_calls, [])

    def test_setgid_failure(self):

        def _setgid(*args):
            raise OSError()

        exc = None
        orig_setgid = service.setgid
        try:
            service.setgid = _setgid
            service.droppriv('user', 'group')
        except Exception, err:
            exc = err
        finally:
            service.setgid = orig_setgid
        self.assertEquals(str(exc),
                          "Permission denied when switching to group 'group'.")
        self.assertEquals(self.setgroups_calls, [([],)])
        # This also asserts setuid is not called before setgid.
        self.assertEquals(self.setuid_calls, [])
        self.assertEquals(self.setgid_calls, [])
        self.assertEquals(self.os_umask_calls, [])
        self.assertEquals(self.setsid_calls, [])
        self.assertEquals(self.chdir_calls, [])

    def test_setgroups_failure(self):
        setgroups_calls = []

        def _setgroups(*args):
            setgroups_calls.append(args)
            e = OSError('test')
            e.errno = 0
            raise e

        exc = None
        orig_setgroups = service.setgroups
        try:
            service.setgroups = _setgroups
            service.droppriv('user')
        except Exception, err:
            exc = err
        finally:
            service.setgroups = orig_setgroups
        self.assertEquals(str(exc), 'test')
        self.assertEquals(setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [])
        self.assertEquals(self.setgid_calls, [])
        self.assertEquals(self.os_umask_calls, [])
        self.assertEquals(self.setsid_calls, [])
        self.assertEquals(self.chdir_calls, [])

    def test_setgroups_perm_failure_ignored(self):
        setgroups_calls = []

        def _setgroups(*args):
            setgroups_calls.append(args)
            e = OSError('test')
            e.errno = EPERM
            raise e

        exc = None
        orig_setgroups = service.setgroups
        try:
            service.setgroups = _setgroups
            service.droppriv('user')
        except Exception, err:
            exc = err
        finally:
            service.setgroups = orig_setgroups
        self.assertEquals(exc, None)
        self.assertEquals(setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [(1,)])
        self.assertEquals(self.setgid_calls, [(2,)])
        self.assertEquals(self.os_umask_calls, [(0022,)])
        self.assertEquals(self.setsid_calls, [()])
        self.assertEquals(self.chdir_calls, [('/',)])

    def test_setsid_failure(self):
        setsid_calls = []

        def _setsid(*args):
            setsid_calls.append(args)
            e = OSError('test')
            e.errno = 0
            raise e

        exc = None
        orig_setsid = service.setsid
        try:
            service.setsid = _setsid
            service.droppriv('user')
        except Exception, err:
            exc = err
        finally:
            service.setsid = orig_setsid
        self.assertEquals(str(exc), 'test')
        self.assertEquals(self.setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [(1,)])
        self.assertEquals(self.setgid_calls, [(2,)])
        self.assertEquals(self.os_umask_calls, [(0022,)])
        self.assertEquals(setsid_calls, [()])
        self.assertEquals(self.chdir_calls, [])

    def test_setsid_perm_failure_ignored(self):
        setsid_calls = []

        def _setsid(*args):
            setsid_calls.append(args)
            e = OSError('test')
            e.errno = EPERM
            raise e

        exc = None
        orig_setsid = service.setsid
        try:
            service.setsid = _setsid
            service.droppriv('user')
        except Exception, err:
            exc = err
        finally:
            service.setsid = orig_setsid
        self.assertEquals(exc, None)
        self.assertEquals(self.setgroups_calls, [([],)])
        self.assertEquals(self.setuid_calls, [(1,)])
        self.assertEquals(self.setgid_calls, [(2,)])
        self.assertEquals(self.os_umask_calls, [(0022,)])
        self.assertEquals(setsid_calls, [()])
        self.assertEquals(self.chdir_calls, [('/',)])


class FakeSocket(object):

    def __init__(self, *args):
        self.init = args
        self.setsockopt_calls = []
        self.bind_calls = []
        self.listen_calls = []

    def setsockopt(self, *args):
        self.setsockopt_calls.append(args)

    def bind(self, *args):
        self.bind_calls.append(args)

    def listen(self, *args):
        self.listen_calls.append(args)


class NonBindingSocket(FakeSocket):

    def bind(self, *args):
        self.bind_calls.append(args)
        exc = socket.error()
        exc.errno = EADDRINUSE
        raise exc


class BadBindSocket(FakeSocket):

    def bind(self, *args):
        exc = socket.error('badbind')
        exc.errno = EPERM
        raise exc


class Test_get_listening_tcp_socket(TestCase):

    def setUp(self):
        self.orig_getaddrinfo = socket.getaddrinfo
        self.orig_socket = socket.socket
        self.orig_time = service.time
        self.orig_sleep = time.sleep
        self.orig_wrap_socket = ssl.wrap_socket
        self.getaddrinfo_calls = []
        self.getaddrinfo_return = ((socket.AF_INET,),)
        self.time_calls = []
        self.time_value = 0
        self.sleep_calls = []
        self.wrap_socket_calls = []

        def _getaddrinfo(*args):
            self.getaddrinfo_calls.append(args)
            return self.getaddrinfo_return

        def _time(*args):
            self.time_calls.append(args)
            self.time_value += 1
            return self.time_value

        def _wrap_socket(*args, **kwargs):
            self.wrap_socket_calls.append((args, kwargs))
            return 'wrappedsock'

        socket.getaddrinfo = _getaddrinfo
        socket.socket = FakeSocket
        service.time = _time
        time.sleep = lambda *a: self.sleep_calls.append(a)
        ssl.wrap_socket = _wrap_socket

    def tearDown(self):
        socket.getaddrinfo = self.orig_getaddrinfo
        socket.socket = self.orig_socket
        service.time = self.orig_time
        time.sleep = self.orig_sleep
        ssl.wrap_socket = self.orig_wrap_socket

    def test_happy_path_inet(self):
        ip = '1.2.3.4'
        port = 5678
        sock = service.get_listening_tcp_socket(ip, port)
        self.assertEquals(self.getaddrinfo_calls,
                          [(ip, port, socket.AF_UNSPEC, socket.SOCK_STREAM)])
        self.assertEquals(sock.init, (socket.AF_INET, socket.SOCK_STREAM))
        self.assertEquals(set(sock.setsockopt_calls), set([
            (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
            (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 600)]))
        self.assertEquals(sock.bind_calls, [((ip, port),)])
        self.assertEquals(sock.listen_calls, [(4096,)])
        self.assertEquals(self.wrap_socket_calls, [])

    def test_happy_path_inet6(self):
        self.getaddrinfo_return = ((socket.AF_INET6,),)
        sock = service.get_listening_tcp_socket('1.2.3.4', 5678)
        self.assertEquals(sock.init, (socket.AF_INET6, socket.SOCK_STREAM))

    def test_uses_passed_backlog(self):
        backlog = 1000
        sock = service.get_listening_tcp_socket('1.2.3.4', 5678, backlog)
        self.assertEquals(sock.listen_calls, [(backlog,)])

    def test_retries(self):
        socket.socket = NonBindingSocket
        exc = None
        try:
            sock = service.get_listening_tcp_socket('1.2.3.4', 5678)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            'Could not bind to 1.2.3.4:5678 after trying for 30 seconds.')
        # Calls time once before loop to calculate when to stop and once per
        # loop to see if it's time to stop.
        self.assertEquals(self.time_value, 31)
        self.assertEquals(len(self.time_calls), 31)
        # Sleeps 29 times and then sees it's been 30s (the default retry time).
        self.assertEquals(len(self.sleep_calls), 29)

    def test_uses_passed_retry(self):
        socket.socket = NonBindingSocket
        exc = None
        try:
            sock = service.get_listening_tcp_socket('1.2.3.4', 5678, retry=10)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            'Could not bind to 1.2.3.4:5678 after trying for 10 seconds.')
        # Calls time once before loop to calculate when to stop and once per
        # loop to see if it's time to stop.
        self.assertEquals(self.time_value, 11)
        self.assertEquals(len(self.time_calls), 11)
        # Sleeps 9 times and then sees it's been 10s.
        self.assertEquals(len(self.sleep_calls), 9)

    def test_wraps_socket(self):
        certfile = 'certfile'
        keyfile = 'keyfile'
        sock = service.get_listening_tcp_socket('1.2.3.4', 5678,
                                                certfile=certfile,
                                                keyfile=keyfile)
        self.assertEquals(sock, 'wrappedsock')
        self.assertEquals(len(self.wrap_socket_calls), 1)
        self.assertEquals(self.wrap_socket_calls[0][1],
                          {'certfile': 'certfile', 'keyfile': 'keyfile'})

    def test_uses_eventlet_socket(self):
        try:
            import eventlet.green.socket
        except ImportError:
            raise SkipTest()
        orig_esocket = eventlet.green.socket.socket
        orig_egetaddrinfo = eventlet.green.socket.getaddrinfo
        egetaddrinfo_calls = []

        def _getaddrinfo(*args):
            egetaddrinfo_calls.append(args)
            return self.getaddrinfo_return

        try:
            # Won't bind unless it uses eventlet's socket.
            socket.socket = NonBindingSocket
            eventlet.green.socket.socket = FakeSocket
            eventlet.green.socket.getaddrinfo = _getaddrinfo
            ip = '1.2.3.4'
            port = 5678
            sock = service.get_listening_tcp_socket(ip, port, style='eventlet')
            self.assertEquals(egetaddrinfo_calls,
                [(ip, port, socket.AF_UNSPEC, socket.SOCK_STREAM)])
            self.assertEquals(sock.init, (socket.AF_INET, socket.SOCK_STREAM))
            self.assertEquals(set(sock.setsockopt_calls), set([
                (socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
                (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
                (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 600)]))
            self.assertEquals(sock.bind_calls, [((ip, port),)])
            self.assertEquals(sock.listen_calls, [(4096,)])
            self.assertEquals(self.wrap_socket_calls, [])
        finally:
            eventlet.green.socket.socket = orig_esocket
            eventlet.green.socket.getaddrinfo = orig_egetaddrinfo

    def test_uses_eventlet_wrap_socket(self):
        try:
            import eventlet.green.socket
            import eventlet.green.ssl
        except ImportError:
            raise SkipTest()
        orig_esocket = eventlet.green.socket.socket
        orig_egetaddrinfo = eventlet.green.socket.getaddrinfo
        orig_ewrap_socket = eventlet.green.ssl.wrap_socket
        egetaddrinfo_calls = []
        ewrap_socket_calls = []

        def _getaddrinfo(*args):
            egetaddrinfo_calls.append(args)
            return self.getaddrinfo_return

        def _ewrap_socket(*args, **kwargs):
            ewrap_socket_calls.append((args, kwargs))
            return 'ewrappedsock'

        try:
            eventlet.green.socket.socket = FakeSocket
            eventlet.green.socket.getaddrinfo = _getaddrinfo
            eventlet.green.ssl.wrap_socket = _ewrap_socket
            certfile = 'certfile'
            keyfile = 'keyfile'
            sock = service.get_listening_tcp_socket('1.2.3.4', 5678,
                style='eventlet', certfile=certfile, keyfile=keyfile)
            self.assertEquals(sock, 'ewrappedsock')
            self.assertEquals(len(ewrap_socket_calls), 1)
            self.assertEquals(ewrap_socket_calls[0][1],
                              {'certfile': 'certfile', 'keyfile': 'keyfile'})
        finally:
            eventlet.green.socket.socket = orig_esocket
            eventlet.green.socket.getaddrinfo = orig_egetaddrinfo
            eventlet.green.ssl.wrap_socket = orig_ewrap_socket

    def test_uses_eventlet_sleep(self):
        try:
            import eventlet
            import eventlet.green.socket
        except ImportError:
            raise SkipTest()
        orig_sleep = eventlet.sleep
        orig_esocket = eventlet.green.socket.socket
        esleep_calls = []
        try:
            eventlet.sleep = lambda *a: esleep_calls.append(a)
            eventlet.green.socket.socket = NonBindingSocket
            exc = None
            try:
                sock = service.get_listening_tcp_socket('1.2.3.4', 5678,
                                                        style='eventlet')
            except Exception, err:
                exc = err
            self.assertEquals(str(exc),
                'Could not bind to 1.2.3.4:5678 after trying for 30 seconds.')
            self.assertEquals(len(esleep_calls), 29)
            self.assertEquals(len(self.sleep_calls), 0)
        finally:
            eventlet.sleep = orig_sleep
            eventlet.green.socket.socket = orig_esocket

    def test_invalid_style(self):
        exc = None
        try:
            service.get_listening_tcp_socket('1.2.3.4', 5678, style='invalid')
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), "Socket style 'invalid' not understood.")

    def test_ip_as_none_is_all(self):
        sock = service.get_listening_tcp_socket(None, 5678)
        self.assertEquals(sock.bind_calls[0][0][0], '0.0.0.0')

    def test_ip_as_star_is_all(self):
        sock = service.get_listening_tcp_socket('*', 5678)
        self.assertEquals(sock.bind_calls[0][0][0], '0.0.0.0')

    def test_no_family_raises_exception(self):
        self.getaddrinfo_return = ((socket.AF_APPLETALK,),)
        exc = None
        try:
            service.get_listening_tcp_socket('1.2.3.4', 5678)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc),
            'Could not determine address family of 1.2.3.4:5678 for binding.')

    def test_odd_exception_reraised(self):
        socket.socket = BadBindSocket
        exc = None
        try:
            service.get_listening_tcp_socket('1.2.3.4', 5678)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), 'badbind')


class Test_signum2str(TestCase):

    def test_signum2str(self):
        self.assertEquals(service.signum2str(1), 'SIGHUP')
        self.assertEquals(service.signum2str(12), 'SIGUSR2')
        self.assertEquals(service.signum2str(999999), 'UNKNOWN')


class FakeLogger(object):

    def __init__(self):
        self.debug_calls = []
        self.info_calls = []
        self.exception_calls = []

    def debug(self, *args):
        self.debug_calls.append(args)

    def info(self, *args):
        self.info_calls.append(args)

    def exception(self, *args):
        self.exception_calls.append(args)


class Test_sustain_workers(TestCase):

    def setUp(self):
        self.orig_sleep = time.sleep
        self.orig_signal = service.signal
        self.orig_fork = service.fork
        self.orig_os_wait = service.os_wait
        self.orig_wifexited = service.WIFEXITED
        self.orig_wifsignaled = service.WIFSIGNALED
        self.orig_killpg = service.killpg
        self.sleep_calls = []
        self.signal_calls = []
        self.killpg_calls = []
        self.worker_func_calls = []
        time.sleep = lambda *a: self.sleep_calls.append(a)
        service.signal = lambda *a: self.signal_calls.append(a)
        service.fork = lambda *a: 1
        service.os_wait = lambda *a: (1, 0)
        service.WIFEXITED = lambda *a: True
        service.WIFSIGNALED = lambda *a: True
        service.killpg = lambda *a: self.killpg_calls.append(a)
        self.worker_func = lambda *a: self.worker_func_calls.append(a)

    def tearDown(self):
        time.sleep = self.orig_sleep
        service.signal = self.orig_signal
        service.fork = self.orig_fork
        service.os_wait = self.orig_os_wait
        service.WIFEXITED = self.orig_wifexited
        service.WIFSIGNALED = self.orig_wifsignaled
        service.killpg = self.orig_killpg

    def test_workers0(self):
        logger = FakeLogger()
        service.sustain_workers(0, self.worker_func, logger)
        self.assertEquals(self.worker_func_calls, [(0,)])
        self.assertEquals(logger.debug_calls,
            [('wid:000 pid:%s Starting inproc worker.' % service.getpid(),)])
        self.assertEquals(logger.info_calls,
            [('Exiting due to workers = 0 mode.',)])

    def test_workers0_no_logger(self):
        service.sustain_workers(0, self.worker_func)
        self.assertEquals(self.worker_func_calls, [(0,)])

    def test_sigterm_exit(self):
        logger = FakeLogger()

        def _os_wait(*args):
            self.signal_calls[0][1]()
            return (1, 0)

        service.os_wait = _os_wait
        service.sustain_workers(1, self.worker_func, logger)
        self.assertEquals(logger.debug_calls, [])
        self.assertEquals(logger.info_calls, [('Exiting due to SIGTERM.',)])
        self.assertEquals(self.killpg_calls, [(0, service.SIGTERM)])

    def test_sighup_exit(self):
        logger = FakeLogger()

        def _os_wait(*args):
            self.signal_calls[1][1]()
            return (1, 0)

        service.os_wait = _os_wait
        service.sustain_workers(1, self.worker_func, logger)
        self.assertEquals(logger.debug_calls, [])
        self.assertEquals(logger.info_calls, [('Exiting due to SIGHUP.',)])
        self.assertEquals(self.killpg_calls, [(0, service.SIGHUP)])

    def test_keyboard_interrupt_exit(self):
        logger = FakeLogger()

        def _os_wait(*args):
            raise KeyboardInterrupt()

        service.os_wait = _os_wait
        service.sustain_workers(1, self.worker_func, logger)
        self.assertEquals(logger.debug_calls, [])
        self.assertEquals(logger.info_calls, [('Exiting due to SIGINT.',)])
        self.assertEquals(self.killpg_calls, [(0, service.SIGINT)])

    def test_no_logger_ok(self):

        def _os_wait(*args):
            raise KeyboardInterrupt()

        service.os_wait = _os_wait
        service.sustain_workers(1, self.worker_func)
        self.assertEquals(self.killpg_calls, [(0, service.SIGINT)])

    def test_oserror_unknown_reraise(self):
        logger = FakeLogger()

        def _os_wait(*args):
            raise OSError('testing')

        service.os_wait = _os_wait
        exc = None
        try:
            service.sustain_workers(1, self.worker_func, logger)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), 'testing')

    def test_oserror_eintr_cycle(self):
        logger = FakeLogger()
        self.called = [0]

        def _os_wait(*args):
            self.called[0] += 1
            if self.called[0] == 2:
                raise KeyboardInterrupt()
            err = OSError('testing')
            err.errno = service.EINTR
            raise err

        service.os_wait = _os_wait
        service.sustain_workers(1, self.worker_func, logger)
        self.assertEquals(logger.debug_calls, [])
        self.assertEquals(logger.info_calls, [('Exiting due to SIGINT.',)])
        self.assertEquals(self.killpg_calls, [(0, service.SIGINT)])
        self.assertEquals(self.called[0], 2)

    def test_oserror_echild_cycle(self):
        logger = FakeLogger()
        self.called = [0]

        def _os_wait(*args):
            self.called[0] += 1
            if self.called[0] == 2:
                raise KeyboardInterrupt()
            err = OSError('testing')
            err.errno = service.ECHILD
            raise err

        service.os_wait = _os_wait
        service.sustain_workers(1, self.worker_func, logger)
        self.assertEquals(logger.debug_calls, [])
        self.assertEquals(logger.info_calls, [('Exiting due to SIGINT.',)])
        self.assertEquals(self.killpg_calls, [(0, service.SIGINT)])
        self.assertEquals(self.called[0], 2)

    def test_child(self):
        logger = FakeLogger()
        service.fork = lambda *a: 0
        service.sustain_workers(1, self.worker_func, logger)
        # Asserts the TERM and HUP signal handlers are cleared with the child.
        self.assertEquals(set(self.signal_calls[-2:]),
            set([(service.SIGHUP, 0), (service.SIGTERM, 0)]))
        self.assertEquals(self.worker_func_calls, [(0,)])
        self.assertEquals(logger.debug_calls, [
            ('wid:000 ppid:%s pid:%s Starting worker.' %
                (service.getppid(), service.getpid()),),
            ('wid:000 ppid:%s pid:%s Worker exited.' %
                (service.getppid(), service.getpid()),)])
        self.assertEquals(logger.info_calls, [])

    def test_child_exception(self):

        def _worker_func(*args):
            raise Exception('testing')

        logger = FakeLogger()
        service.fork = lambda *a: 0
        exc = None
        try:
            service.sustain_workers(1, _worker_func, logger)
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), 'testing')
        self.assertEquals(logger.debug_calls, [
            ('wid:000 ppid:%s pid:%s Starting worker.' %
                (service.getppid(), service.getpid()),)])
        self.assertEquals(logger.info_calls, [])
        self.assertEquals(logger.exception_calls, [
            ('wid:000 ppid:%s pid:%s Worker exited due to exception: testing' %
                (service.getppid(), service.getpid()),)])

    def test_no_sleep_on_initial_launch(self):
        fork_calls = []

        def _os_wait(*args):
            raise KeyboardInterrupt()

        def _fork(*args):
            fork_calls.append(args)
            return len(fork_calls)

        service.os_wait = _os_wait
        service.fork = _fork
        service.sustain_workers(5, self.worker_func)
        self.assertEquals(fork_calls, [()] * 5)
        self.assertEquals(self.sleep_calls, [])

    def test_sleep_on_relaunches(self):
        fork_calls = []

        def _os_wait_int(*args):
            raise KeyboardInterrupt()

        def _os_wait(*args):
            service.os_wait = _os_wait_int
            return 1, 0

        def _fork(*args):
            fork_calls.append(args)
            return len(fork_calls)

        service.os_wait = _os_wait
        service.fork = _fork
        service.sustain_workers(5, self.worker_func)
        self.assertEquals(fork_calls, [()] * 6)
        self.assertEquals(self.sleep_calls, [(1,)])


if __name__ == '__main__':
    main()
