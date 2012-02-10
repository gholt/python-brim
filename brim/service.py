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
Provides functions useful for services, such as network daemons,
background jobs, etc.
"""

import sys
from errno import EADDRINUSE, ECHILD, EINTR, EPERM
from grp import getgrnam
from os import chdir, devnull, dup2, fork, getegid, geteuid, getpid, getppid, \
    killpg, setgid, setgroups, setsid, setuid, umask as os_umask, \
    wait as os_wait, WIFEXITED, WIFSIGNALED
from pwd import getpwnam
from signal import SIG_DFL, SIGHUP, SIG_IGN, SIGINT, signal, SIGTERM
from sys import platform
from time import time


_captured_exception = None
_captured_stdout = None
_captured_stderr = None


def _capture_exception(exctype, value, traceback):
    if _captured_exception:
        _captured_exception(exctype, value, traceback)


class _CaptureFile(object):

    def __init__(self, stdout=False, stderr=False):
        self.stdout = stdout
        self.stderr = stderr
        self.buf = []

    def close(self):
        self.flush()

    def flush(self):
        if self.buf:
            out = ''.join(self.buf)
            self.buf = []
            if out:
                if self.stdout and _captured_stdout:
                    _captured_stdout(out)
                if self.stderr and _captured_stderr:
                    _captured_stderr(out)

    def write(self, value):
        value = str(value)
        if value:
            lead, sep, tail = value.rpartition('\n')
            if sep:
                self.buf.append(lead)
                self.buf.append(sep)
                self.flush()
            if tail:
                self.buf.append(tail)

    def writelines(self, lines):
        self.write(''.join(lines))


def capture_exceptions_stdout_stderr(exceptions=None, stdout_func=None,
                                     stderr_func=None):
    """
    Captures uncaught exceptions and redirects them to the
    *exceptions* function and captures standard output and error and
    redirects that data to the stdout_func and stderr_func functions.
    The original standard output and error files will be closed so
    that no output can come from your program to these streams. This
    is useful when writing background daemons that often have no
    connected console.

    The *exceptions* function will be called with (exctype, value,
    traceback).

    The *stdout_func* and *stderr_func* functions will be called with
    (str).
    """
    global _captured_exception, _captured_stdout, _captured_stderr
    _captured_exception = exceptions
    _captured_stdout = stdout_func
    _captured_stderr = stderr_func
    sys.excepthook = _capture_exception
    stdo_files = [sys.stdout, sys.stderr]
    with open(devnull, 'r+b') as nullfile:
        for f in stdo_files:
            if hasattr(f, 'flush'):
                f.flush()
            if hasattr(f, 'fileno'):
                try:
                    dup2(nullfile.fileno(), f.fileno())
                except OSError:
                    pass
    sys.stdout = _CaptureFile(stdout=True)
    sys.stderr = _CaptureFile(stderr=True)


def droppriv(user, group=None, umask=0022):
    """
    Drops privileges to the user, group, and umask given, changes the
    process to session leader, and changes working directories to /.
    If a group is not given, the user's default group will be used.
    Will raise an Exception with an explanatory message if the user
    or group cannot be found or if permission is denied while
    attempting the switch.

    :param user: The user to switch to.
    :param group: The group to switch to; defaults to the default
                  group of the user.
    :param umask: The umask to set; defaults 0022.
    """
    if user or group:
        uid = geteuid()
        try:
            setgroups([])
        except OSError, err:
            if err.errno != EPERM:
                raise
        gid = getegid()
        if user:
            try:
                pw = getpwnam(user)
            except KeyError, err:
                raise Exception('Cannot switch to unknown user %r.' % user)
            uid = pw.pw_uid
            gid = pw.pw_gid
        if group:
            try:
                gr = getgrnam(group)
            except KeyError, err:
                raise Exception('Cannot switch to unknown group %r.' % group)
            gid = gr.gr_gid
        try:
            setgid(gid)
        except OSError, err:
            raise Exception(
                'Permission denied when switching to group %r.' % group)
        try:
            setuid(uid)
        except OSError, err:
            raise Exception(
                'Permission denied when switching to user %r.' % user)
    os_umask(umask)
    try:
        setsid()  # Become session leader until already so.
    except OSError, err:
        if err.errno != EPERM:
            raise
    chdir('/')


def get_listening_tcp_socket(ip, port, backlog=4096, retry=30, certfile=None,
                             keyfile=None, style=None):
    """
    Returns a socket.socket bound to the given ip and tcp port with
    other optional parameters.

    :param ip: The ip address to listen on. ``''`` and ``'*'`` are
               translated to ``'0.0.0.0'`` which will listen on all
               configured addresses.
    :param port: The tcp port to listen on.
    :param backlog: The amount of system queued connections allowed.
    :param retry: The number seconds to keep trying to bind the
                  socket, in case there's another process bound but
                  exiting soon. This allows near zero-downtime
                  process handoffs as you start the new one and kill
                  the old.
    :param certfile: The certificate file if you wish the socket to
                     be ssl wrapped (see ssl.wrap_socket).
    :param keyfile: The key file if you wish the socket to be ssl
                    wrapped (see ssl.wrap_socket).
    :param style: The libraries you'd like to use in creating the
                  socket. The default will use the standard Python
                  libraries. ``'Eventlet'`` is recognized and will
                  use the Eventlet libraries. Other styles may added
                  in the future.
    """
    if not style:
        from socket import AF_INET, AF_INET6, AF_UNSPEC, \
            error as socket_error, getaddrinfo, IPPROTO_TCP, socket, \
            SOCK_STREAM, SO_KEEPALIVE, SOL_SOCKET, SO_REUSEADDR, TCP_KEEPIDLE
        from ssl import wrap_socket
        from time import sleep
    elif style.lower() == 'eventlet':
        from eventlet.green.socket import AF_INET, AF_INET6, AF_UNSPEC, \
            error as socket_error, getaddrinfo, IPPROTO_TCP, socket, \
            SOCK_STREAM, SO_KEEPALIVE, SOL_SOCKET, SO_REUSEADDR, TCP_KEEPIDLE
        from eventlet.green.ssl import wrap_socket
        from eventlet import sleep
    else:
        from socket import error as socket_error
        raise socket_error('Socket style %r not understood.' % style)
    if not ip or ip == '*':
        ip = '0.0.0.0'
    family = None
    for a in getaddrinfo(ip, port, AF_UNSPEC, SOCK_STREAM):
        if a[0] in (AF_INET, AF_INET6):
            family = a[0]
            break
    if not family:
        raise socket_error('Could not determine address family of %s:%s for '
                           'binding.' % (ip, port))
    good_sock = None
    retry_until = time() + retry
    while not good_sock and time() < retry_until:
        try:
            sock = socket(family, SOCK_STREAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            sock.setsockopt(SOL_SOCKET, SO_KEEPALIVE, 1)
            sock.setsockopt(IPPROTO_TCP, TCP_KEEPIDLE, 600)
            sock.bind((ip, port))
            sock.listen(backlog)
            if certfile and keyfile:
                sock = wrap_socket(sock, certfile=certfile, keyfile=keyfile)
            good_sock = sock
        except socket_error, err:
            if err.errno != EADDRINUSE:
                raise
            sleep(0.1)
    if not good_sock:
        raise socket_error('Could not bind to %s:%s after trying for %s '
                           'seconds.' % (ip, port, retry))
    return good_sock


def get_listening_udp_socket(ip, port, retry=30, style=None):
    """
    Returns a socket.socket bound to the given ip and tcp port with
    other optional parameters.

    :param ip: The ip address to listen on. ``''`` and ``'*'`` are
               translated to ``'0.0.0.0'`` which will listen on all
               configured addresses.
    :param port: The udp port to listen on.
    :param retry: The number seconds to keep trying to bind the
                  socket, in case there's another process bound but
                  exiting soon. This allows near zero-downtime
                  process handoffs as you start the new one and kill
                  the old.
    :param style: The libraries you'd like to use in creating the
                  socket. The default will use the standard Python
                  libraries. ``'Eventlet'`` is recognized and will
                  use the Eventlet libraries. Other styles may added
                  in the future.
    """
    if not style:
        from socket import AF_INET, AF_INET6, AF_UNSPEC, \
            error as socket_error, getaddrinfo, socket, SOCK_DGRAM, \
            SOL_SOCKET, SO_REUSEADDR
        from time import sleep
    elif style.lower() == 'eventlet':
        from eventlet.green.socket import AF_INET, AF_INET6, AF_UNSPEC, \
            error as socket_error, getaddrinfo, socket, SOCK_DGRAM, \
            SOL_SOCKET, SO_REUSEADDR
        from eventlet import sleep
    else:
        from socket import error as socket_error
        raise socket_error('Socket style %r not understood.' % style)
    if not ip or ip == '*':
        ip = '0.0.0.0'
    family = None
    for a in getaddrinfo(ip, port, AF_UNSPEC, SOCK_DGRAM):
        if a[0] in (AF_INET, AF_INET6):
            family = a[0]
            break
    if not family:
        raise socket_error('Could not determine address family of %s:%s for '
                           'binding.' % (ip, port))
    good_sock = None
    retry_until = time() + retry
    while not good_sock and time() < retry_until:
        try:
            sock = socket(family, SOCK_DGRAM)
            sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            sock.bind((ip, port))
            good_sock = sock
        except socket_error, err:
            if err.errno != EADDRINUSE:
                raise
            sleep(0.1)
    if not good_sock:
        raise socket_error('Could not bind to %s:%s after trying for %s '
                           'seconds.' % (ip, port, retry))
    return good_sock


def signum2str(signum):
    """
    Translates a signal number to a str. Example::

        >>> print signum2str(1)
        SIGHUP

    :param signum: The signal number to convert.
    :returns: A str representing the signal.
    """
    import signal
    for attr in dir(signal):
        if attr.startswith('SIG') and getattr(signal, attr) == signum:
            return attr
    return 'UNKNOWN'


def sustain_workers(workers_desired, worker_func, logger=None):
    """
    Starts and maintains a set of subprocesses. For each worker
    started, it will run the *worker_func*. If a subprocess exits
    without being requested to, it will be restarted and the
    *worker_func* called again.

    *sustain_workers* will not return until signaled to do so with
    SIGHUP or SIGTERM to the main process. These signals will be
    relayed to the subprocesses as well.

    SIGHUP generally means the processes should exit as gracefully as
    possible. For instance, a web server might exit after it
    completes any requests already in progress.

    SIGTERM generally means the processes should exit immediately,
    canceling anything they may have been doing at the time.

    If *workers_desired* is 0, a special "inproc" mode will be
    activated where just the *worker_func* will be called and then
    *sustain_workers* will return. This can be useful for debugging.

    See brim.server.Server for a good example of how to use
    *sustain_workers*.

    :param workers_desired: The number of subprocesses desired to be
                            maintained. If 0, no subprocesses will be
                            made and *worker_func* will simply be
                            called and then *sustain_workers* will
                            return.
    :param worker_func: The function to be called by each subprocess
                        once it starts. *worker_func* should not
                        return except on catastrophic error or when
                        signaled to do so. If *worker_func* exits
                        without being signaled, another subprocess
                        will be started and the function called
                        again.
    :param logger: If set, debug information will be sent to this
                   logging.Logger instance.
    """
    from time import sleep
    if workers_desired == 0:
        if logger:
            logger.debug('wid:000 pid:%s Starting inproc worker.' % getpid())
        worker_func(0)
        if logger:
            logger.info('Exiting due to workers = 0 mode.')
        return

    signal_received = [0]

    def term_signal(*args):
        signal(SIGTERM, SIG_IGN)
        signal_received[0] = SIGTERM

    def hup_signal(*args):
        signal(SIGHUP, SIG_IGN)
        signal_received[0] = SIGHUP

    signal(SIGTERM, term_signal)
    signal(SIGHUP, hup_signal)
    worker_pids = [0] * workers_desired
    initial_forking = True
    while not signal_received[0]:
        while True:
            try:
                worker_id = worker_pids.index(0)
            except ValueError:
                break
            pid = fork()
            if pid == 0:
                signal(SIGTERM, SIG_DFL)
                signal(SIGHUP, SIG_DFL)
                ppid = getppid()
                if logger:
                    logger.debug('wid:%03d ppid:%d pid:%d Starting worker.' %
                                 (worker_id, ppid, getpid()))
                try:
                    worker_func(worker_id)
                except Exception, err:
                    if logger:
                        logger.exception('wid:%03d ppid:%d pid:%d Worker '
                            'exited due to exception: %s' %
                            (worker_id, ppid, getpid(), err))
                    # Reraised in case of useful installed sys.excepthook.
                    raise
                if logger:
                    logger.debug('wid:%03d ppid:%d pid:%d Worker exited.' %
                                 (worker_id, ppid, getpid()))
                return
            else:
                worker_pids[worker_id] = pid
                if not initial_forking:
                    # This means that after the initial forking, subprocesses
                    # will be reforked at a maximum rate of one per second.
                    sleep(1)
        initial_forking = False
        try:
            pid, status = os_wait()
            if WIFEXITED(status) or WIFSIGNALED(status):
                worker_pids[worker_pids.index(pid)] = 0
        except OSError, err:
            if err.errno not in (EINTR, ECHILD):
                raise
        except KeyboardInterrupt:
            signal_received[0] = SIGINT
            break
    if logger:
        logger.info('Exiting due to %s.' % signum2str(signal_received[0]))
    killpg(0, signal_received[0])
