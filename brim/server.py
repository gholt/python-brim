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
The main module that implements the Brim.Net Core Server. Normally
you don't directly use this module but instead configure and run
brimd.

See etc/brimd.conf-sample for configuration options.
"""

from ctypes import c_uint, c_ulong, sizeof as ctypes_sizeof
from errno import EBADF, EINVAL, ENOENT, ESRCH
from inspect import getargspec
from mmap import mmap
from optparse import OptionParser
from os import fork, environ, kill, unlink
from signal import signal, SIGHUP, SIGTERM
from socket import error as socket_error
from sys import argv as sys_argv, stdin as sys_stdin, stdout as sys_stdout, \
    stderr as sys_stderr
from time import gmtime, strftime, time
from traceback import format_exception
from urllib import unquote, unquote_plus
from uuid import uuid4

from brim.conf import read_conf, TRUE_VALUES
from brim.service import capture_exceptions_stdout_stderr, droppriv, \
    get_listening_tcp_socket, get_listening_udp_socket, sustain_workers
from eventlet import GreenPool, sleep, wsgi
from eventlet.greenio import shutdown_safe
from eventlet.hubs import use_hub

import brim
from brim.log import get_logger, sysloggable_excinfo

try:
    from setproctitle import setproctitle
except ImportError:
    setproctitle = None


#: The list of default conf files to use when none are specified.
DEFAULT_CONF_FILES = ['/etc/brimd.conf', '~/.brimd.conf']
#: The status code logged for requests terminated early by the client
#: (499).
HTTP_CLIENT_DISCONNECT = 499
#: The number of seconds to wait for a PID to disappear after sending
#: an appropriate signal.
PID_WAIT_TIME = 15


def _send_pid_sig(pid_file, sig, expect_exit=False, pid_override=None):
    """
    Utility method for sending a signal to an existing brimd
    process as found in the pid file.

    :param sig: The signal to send, such as signal.SIGHUP.
    :param expect_exit: Set True if the existing process is
                        expected to exit after the signal and
                        this method will wait PID_WAIT_TIME for
                        that to happen or raise an Exception.
                        Default: False.
    :param pid_override: Set to a pid and this method will not
                         attempt to read the pid from the pid
                         file.
    :returns: (success, pid) where success is True if the signal
              was sent without error and pid is that of the
              process that the signal was sent to.
    """
    pid = pid_override
    if not pid:
        try:
            with open(pid_file) as open_pid_file:
                pid = int(open_pid_file.read().strip())
        except IOError, err:
            if err.errno != ENOENT:
                raise
        except ValueError:
            # We just ignore pid files that don't have an int.
            pass
    if pid:
        try:
            kill(pid, sig)
            if expect_exit:
                wait_until = time() + PID_WAIT_TIME
                while True:
                    try:
                        kill(pid, 0)
                    except OSError, err:
                        if err.errno == ESRCH:
                            break
                        raise
                    if time() >= wait_until:
                        raise Exception(
                            '%s did not exit after %s seconds.' %
                            (pid, PID_WAIT_TIME))
                    sleep(1)
                if not pid_override:
                    try:
                        unlink(pid_file)
                    except OSError, err:
                        if err.errno != ENOENT:
                            raise
            return (True, pid)
        except OSError, err:
            if err.errno == ESRCH:
                return (False, pid)
            else:
                raise
    return (False, 0)


def _log_quote(value):
    return ''.join(_log_quote_chars(value))


def _log_quote_chars(value):
    for c in value:
        if c < '!' or c == '%' or c > '~':
            yield '%%%02X' % ord(c)
        else:
            yield c


class _BucketStats(object):
    """
    This is used to track server stats by allocating a shared memory
    mmap. Each daemon or worker writes to just its own areas and
    apps like brim.stats.Stats can read and report on all of
    them.

    stats_conf is a dict whose keys are the stat names and whose
    values are the stat types. The types are used to interpret how to
    rollup the bucket stats into overall stats. Types are:

    * worker: Not rolled up; used for within a bucket only.
    * sum: All bucket values for the stat will be added together and
           reported as the overall stat.
    * min: The minimum value of the stat for all buckets will be
           reported as the overall stat.
    * max: The maximum value of the stat for all buckets will be
           reported as the overall stat.
    """

    def __init__(self, bucket_names, stats_conf):
        self.bucket_names = bucket_names
        self.bucket_count = len(bucket_names)
        self.stats_conf = stats_conf
        if self.bucket_count:
            self._stats = [{} for x in xrange(self.bucket_count)]
            c_ulong_size = ctypes_sizeof(c_ulong)
            self._mmap = \
                mmap(-1, self.bucket_count * len(stats_conf) * c_ulong_size)
            offset = 0
            for bucket_id in xrange(self.bucket_count):
                for name in stats_conf:
                    v = c_ulong.from_buffer(self._mmap, offset)
                    offset += c_ulong_size
                    v.value = 0
                    self._stats[bucket_id][name] = v

    def get(self, bucket_id, name):
        if not self.bucket_count:
            return 0
        v = self._stats[bucket_id].get(name)
        return v.value if v else 0

    def set(self, bucket_id, name, value):
        if self.bucket_count:
            v = self._stats[bucket_id].get(name)
            if v is not None:
                v.value = int(value)

    def incr(self, bucket_id, name):
        if self.bucket_count:
            v = self._stats[bucket_id].get(name)
            if v is not None:
                v.value += 1


class _Stats(object):
    """
    Similar to _BucketStats except that it's bound to just one
    bucket_id, representing a daemon or worker. For daemons and
    non-WSGI apps, this is passed directly in the ``__call__`` call.
    For WSGI workers, this is passed with each request in
    env['brim.stats'].
    """

    def __init__(self, bucket_stats, bucket_id):
        self.bucket_stats = bucket_stats
        self.bucket_id = bucket_id

    def get(self, name):
        return self.bucket_stats.get(self.bucket_id, name)

    def set(self, name, value):
        self.bucket_stats.set(self.bucket_id, name, value)

    def incr(self, name):
        self.bucket_stats.incr(self.bucket_id, name)


class _EventletWSGINullLogger():
    """
    Simple class to throw away anything Eventlet's WSGI layer tries
    to log.
    """

    def write(self, *args):
        pass


class _WsgiInput(object):
    """
    A wrapper used around WSGI env['wsgi.input'] to track the number
    of bytes received for later logging.
    """

    def __init__(self, env, iter_chunk_size):
        self.env = env
        self.flo = self.env['wsgi.input']
        self.env['wsgi.input'] = self
        self.iter_chunk_size = iter_chunk_size

    def __iter__(self):
        return self

    def close(self):
        self.flo.close()

    def flush(self):
        self.flo.flush()

    def fileno(self):
        self.flo.fileno()

    def next(self):
        rv = self.read(self.iter_chunk_size)
        if not rv:
            raise StopIteration
        return rv

    def read(self, size=None):
        if size:
            rv = self.flo.read(size)
        else:
            rv = self.flo.read()
        self.env['brim._bytes_in'] += len(rv)
        return rv

    def readline(self, size=None):
        if size:
            rv = self.flo.readline(size)
        else:
            rv = self.flo.readline()
        self.env['brim._bytes_in'] += len(rv)
        return rv

    def readlines(self, sizehint=None):
        if sizehint:
            rv = self.flo.readlines(sizehint)
        else:
            rv = self.flo.readlines()
        for line in rv:
            self.env['brim._bytes_in'] += len(line)
        return rv


class _WsgiOutput(object):
    """
    A wrapper used around WSGI body iterables to track the number of
    bytes sent for later logging.
    """

    def __init__(self, body, env):
        self.body = iter(body)
        self.env = env

    def __iter__(self):
        return self

    def next(self):
        rv = self.body.next()
        self.env['brim._bytes_out'] += len(rv)
        return rv


class Subserver(object):
    """
    Created for each [wsgi], [wsgi2], etc., [tcp], [tcp2], etc.
    [udp], [udp2], etc., and [daemons] config section to hold the
    attributes specific to that subconfig.

    :param server: The parent brim.server.Server.
    :param name: The name of the subserver ('wsgi', 'tcp', 'udp',
                 'daemons', etc.)
    """

    def __init__(self, server, name):
        #: The parent brim.server.Server of this subserver.
        self.server = server
        #: The logger in use by this subserver. WSGI apps can also access this
        #: via ``env['brim.logger']``.
        self.logger = None
        #: The json.dumps compatible function configured. WSGI apps can also
        #: access this via ``env['brim.json_dumps']``.
        self.json_dumps = None
        #: The json.loads compatible function configured. WSGI apps can also
        #: access this via ``env['brim.json_loads']``.
        self.json_loads = None
        self.name = name
        self.worker_count = 1
        self.worker_names = ['0']
        self.stats_conf = {'start_time': 'worker'}

    def _parse_conf(self, conf):
        """
        Translates the brim.conf.Conf configuration into instance
        attributes for use later. This ensures we have a good
        configuration before we try starting the server.

        :param conf: The brim.conf.Conf instance for the overall
                     server configuration.
        """
        self.log_name = conf.get(self.name, 'log_name',
            conf.get('brim', 'log_name', 'brim') + self.name)
        self.log_level = conf.get(self.name, 'log_level',
            conf.get('brim', 'log_level', 'INFO')).upper()
        try:
            import logging
            getattr(logging, self.log_level)
        except AttributeError:
            raise Exception(
                'Invalid [%s] log_level %r.' % (self.name, self.log_level))
        self.log_facility = conf.get(self.name, 'log_facility',
            conf.get('brim', 'log_facility', 'LOCAL0')).upper()
        if not self.log_facility.startswith('LOG_'):
            self.log_facility = 'LOG_' + self.log_facility
        try:
            from logging.handlers import SysLogHandler
            getattr(SysLogHandler, self.log_facility)
        except AttributeError:
            raise Exception('Invalid [%s] log_facility %r.' %
                            (self.name, self.log_facility))
        self.json_dumps = conf.get(self.name, 'json_dumps',
            conf.get('brim', 'json_dumps', 'json.dumps'))
        try:
            mod, fnc = self.json_dumps.rsplit('.', 1)
        except ValueError:
            raise Exception('Invalid [%s] json_dumps value %r.' %
                            (self.name, self.json_dumps))
        try:
            self.json_dumps = getattr(__import__(mod, fromlist=[fnc]), fnc)
        except (AttributeError, ImportError):
            raise Exception(
                'Could not load function %r for [%s] json_dumps.' %
                (self.json_dumps, self.name))
        self.json_loads = conf.get(self.name, 'json_loads',
            conf.get('brim', 'json_loads', 'json.loads'))
        try:
            mod, fnc = self.json_loads.rsplit('.', 1)
        except ValueError:
            raise Exception('Invalid [%s] json_loads value %r.' %
                            (self.name, self.json_loads))
        try:
            self.json_loads = getattr(__import__(mod, fromlist=[fnc]), fnc)
        except (AttributeError, ImportError):
            raise Exception(
                'Could not load function %r for [%s] json_loads.' %
                (self.json_loads, self.name))

    def _privileged_start(self):
        """
        Called just before dropping privileges and calling _start.
        Should be used to bind to privileged ports and anything else
        that might need greater privileges.
        """
        pass

    def _start(self, bucket_stats):
        """
        This is the last method run by the main brimd server process.

        :param bucket_stats: The _BucketStats instance for use by
                             this subserver.
        """
        self.bucket_stats = bucket_stats


class IPSubserver(Subserver):
    """
    Created for each [wsgi], [wsgi2], etc., [tcp], [tcp2], etc.
    [udp], [udp2], etc. config section to hold the attributes
    specific to that subconfig.

    :param server: The parent brim.server.Server.
    :param name: The name of the subserver ('wsgi', 'tcp', 'udp',
                 etc.)
    """

    def __init__(self, server, name):
        Subserver.__init__(self, server, name)

    def _parse_conf(self, conf):
        Subserver._parse_conf(self, conf)
        self.ip = conf.get(self.name, 'ip', conf.get('brim', 'ip', '*'))
        self.port = conf.get_int(self.name, 'port',
            conf.get_int('brim', 'port', 80))
        if self.server.no_daemon:
            self.worker_count = 0
            self.worker_names = ['0']
        else:
            self.worker_count = conf.get_int(self.name, 'workers',
                conf.get_int('brim', 'workers', 1))
            self.worker_names = \
                [str(i) for i in xrange(self.worker_count or 1)]
        self.certfile = conf.get(self.name, 'certfile',
            conf.get('brim', 'certfile'))
        self.keyfile = conf.get(self.name, 'keyfile',
            conf.get('brim', 'keyfile'))
        self.client_timeout = conf.get_int(self.name, 'client_timeout',
            conf.get_int('brim', 'client_timeout', 60))
        self.concurrent_per_worker = \
            conf.get_int(self.name, 'concurrent_per_worker',
                conf.get_int('brim', 'concurrent_per_worker', 1024))
        self.backlog = conf.get_int(self.name, 'backlog',
            conf.get_int('brim', 'backlog', 4096))
        self.listen_retry = conf.get_int(self.name, 'listen_retry',
            conf.get_int('brim', 'listen_retry', 30))
        self.eventlet_hub = conf.get(self.name, 'eventlet_hub',
            conf.get('brim', 'eventlet_hub', 'poll'))


class WSGISubserver(IPSubserver):
    """
    Created for each [wsgi], [wsgi2], [wsgi3] config section to hold the
    attributes specific to that subconfig. Few WSGI apps need to
    access this directly, but some like brim.stats.Stats do.

    :param server: The parent brim.server.Server.
    :param name: The name of the subserver ('wsgi', 'wsgi2', 'wsgi3',
                 etc.)
    """

    def __init__(self, server, name):
        IPSubserver.__init__(self, server, name)
        self.stats_conf.update({'request_count': 'sum',
            'status_2xx_count': 'sum', 'status_3xx_count': 'sum',
            'status_4xx_count': 'sum', 'status_5xx_count': 'sum'})

    def _parse_conf(self, conf):
        IPSubserver._parse_conf(self, conf)
        self.log_headers = conf.get_boolean(self.name, 'log_headers',
            conf.get_boolean('brim', 'log_headers', False))
        self.count_status_codes = conf.get(self.name, 'count_status_codes',
            conf.get('brim', 'count_status_codes', '404 408 499 501'))
        try:
            self.count_status_codes = [int(c) for c in
                self.count_status_codes.split()]
        except ValueError:
            raise Exception('Invalid [%s] count_status_codes %r.' %
                            (self.name, self.count_status_codes))
        self.wsgi_input_iter_chunk_size = \
            conf.get_int(self.name, 'wsgi_input_iter_chunk_size',
                conf.get_int('brim', 'wsgi_input_iter_chunk_size', 4096))

        self.apps = []
        app_names = conf.get(self.name, 'apps', '').strip().split()
        for app_name in app_names:
            call = conf.get(app_name, 'call')
            if not call:
                raise Exception(
                    "App [%s] not configured with 'call' option." % app_name)
            try:
                mod, cls = call.rsplit('.', 1)
            except ValueError:
                raise Exception(
                    'Invalid call value %r for app [%s].' % (call, app_name))
            try:
                app_class = getattr(__import__(mod, fromlist=[cls]), cls)
            except (AttributeError, ImportError):
                raise Exception(
                    'Could not load class %r for app [%s].' % (call, app_name))
            try:
                args = len(getargspec(app_class.__init__).args)
                if args != 4:
                    raise Exception('Would not be able to instantiate %r for '
                        'app [%s]. Incorrect number of args, %s, should be 4 '
                        '(self, name, conf, next_app).' %
                        (call, app_name, args))
            except TypeError, err:
                if str(err) == 'arg is not a Python function':
                    err = 'Probably not a class.'
                raise Exception(
                    'Would not be able to instantiate %r for app [%s]. %s' %
                    (call, app_name, err))
            try:
                args = len(getargspec(app_class.__call__).args)
                if args != 3:
                    raise Exception('Would not be able to use %r for app '
                        '[%s]. Incorrect number of __call__ args, %s, should '
                        'be 3 (self, env, start_response).' %
                        (call, app_name, args))
            except TypeError, err:
                if str(err) == 'arg is not a Python function':
                    err = 'Probably no __call__ method.'
                raise Exception(
                    'Would not be able to use %r for app [%s]. %s' %
                    (call, app_name, err))
            if hasattr(app_class, 'parse_conf'):
                try:
                    args = len(getargspec(app_class.parse_conf).args)
                    if args != 3:
                        raise Exception('Cannot use %r for app [%s]. '
                            'Incorrect number of parse_conf args, %s, should '
                            'be 3 (cls, name, conf).' %
                            (call, app_name, args))
                except TypeError, err:
                    if str(err) == 'arg is not a Python function':
                        err = 'parse_conf probably not a method.'
                    raise Exception('Cannot use %r for app [%s]. %s' %
                                    (call, app_name, err))
                app_conf = app_class.parse_conf(app_name, conf)
            else:
                app_conf = conf
            if hasattr(app_class, 'stats_conf'):
                try:
                    args = len(getargspec(app_class.stats_conf).args)
                    if args != 3:
                        raise Exception('Cannot use %r for app [%s]. '
                            'Incorrect number of stats_conf args, %s, should '
                            'be 3 (cls, name, conf).' %
                            (call, app_name, args))
                except TypeError, err:
                    if str(err) == 'arg is not a Python function':
                        err = 'stats_conf probably not a method.'
                    raise Exception('Cannot use %r for app [%s]. %s' %
                                    (call, app_name, err))
                for stat_name, stat_type in \
                        app_class.stats_conf(app_name, app_conf):
                    self.stats_conf[stat_name] = stat_type
            self.apps.append((app_name, app_class, app_conf))

    def _privileged_start(self):
        try:
            self.sock = get_listening_tcp_socket(self.ip, self.port,
                backlog=self.backlog, retry=self.listen_retry,
                certfile=self.certfile, keyfile=self.keyfile, style='eventlet')
        except socket_error, err:
                raise Exception(
                    'Could not bind to %s:%s: %s' % (self.ip, self.port, err))

    def _start(self, bucket_stats):
        IPSubserver._start(self, bucket_stats)
        self.worker_id = -1
        if not self.server.output:
            capture_exceptions_stdout_stderr(
                exceptions=self._capture_exception,
                stdout_func=self._capture_stdout,
                stderr_func=self._capture_stderr)
        self.start_time = int(time())
        self.logger = get_logger(self.name, self.log_name, self.log_level,
                                 self.log_facility, self.server.no_daemon)
        for code in self.count_status_codes:
            self.stats_conf['status_%d_count' % code] = 'sum'
        wsgi.HttpProtocol.default_request_version = 'HTTP/1.0'
        wsgi.HttpProtocol.log_request = lambda *a: None
        wsgi.HttpProtocol.log_message = \
            lambda s, f, *a: self.logger.error('WSGI ERROR: ' + f % a)
        wsgi.WRITE_TIMEOUT = self.client_timeout
        sustain_workers(self.worker_count, self._wsgi_worker,
                        logger=self.logger)
        if self.worker_id == -1:
            shutdown_safe(self.sock)
            self.sock.close()

    def _wsgi_worker(self, worker_id):
        """
        This method is called for each WSGI worker subprocess spawned
        and it simply constructs all the configured WSGI applications
        and then begins sending incoming requests to them (via
        Eventlet WSGI layer and our _wsgi_entry below).
        """
        if setproctitle:
            if not self.server.no_daemon:
                setproctitle('%d:%s:brimd' % (worker_id, self.name))
        self.worker_id = worker_id
        self.bucket_stats.set(worker_id, 'start_time', time())
        if not self.server.no_daemon:
            use_hub(self.eventlet_hub)
        self.first_app = self
        for app_name, app_class, app_conf in reversed(self.apps):
            self.first_app = app_class(app_name, app_conf, self.first_app)
        pool = GreenPool(size=self.concurrent_per_worker)
        try:
            wsgi.server(self.sock, self._wsgi_entry, _EventletWSGINullLogger(),
                        custom_pool=pool)
        except socket_error, err:
            if err.errno != EINVAL:
                raise
        pool.waitall()

    def _wsgi_entry(self, env, start_response):
        """
        Called by Eventlet's WSGI layer to handle incoming requests.
        This wraps the request handling to add additional WSGI env
        values, count the bytes transmitted and received, and log the
        request/response once it has completed.
        """

        def _start_response(status, headers, exc_info=None):
            env['brim._start_response'] = (status, headers, exc_info)
            start_response(status, headers, exc_info)

        try:
            env['brim'] = self
            env['brim.start'] = time()
            env['brim.stats'] = _Stats(self.bucket_stats, self.worker_id)
            env['brim.logger'] = self.logger
            env['brim.txn'] = self.logger.txn = uuid4().hex
            env['brim._bytes_in'] = 0
            env['brim._bytes_out'] = 0
            env['wsgi.input'] = \
                _WsgiInput(env, self.wsgi_input_iter_chunk_size)
            env['brim.additional_request_log_info'] = []
            env['brim.json_dumps'] = self.json_dumps
            env['brim.json_loads'] = self.json_loads
            env['eventlet.posthooks'].append((self._log_request, (), {}))
            return _WsgiOutput(self.first_app(env, _start_response), env)
        except Exception, err:
            self.logger.exception('WSGI EXCEPTION:')
            _start_response('500 Internal Server Error',
                            [('Content-Length', '0')])
            return []

    def __call__(self, env, start_response):
        """
        The default WSGI application that simply responds with 404
        Not Found.
        """
        start_response('404 Not Found', [('Content-Length', '0')])
        return []

    def _log_request(self, env):
        """
        After each request has completed, Eventlet calls this method
        and we log the request/response details at the NOTICE log
        level.
        """
        try:
            stats = _Stats(self.bucket_stats, self.worker_id)
            stats.incr('request_count')
            status, headers, exc_info = env['brim._start_response']
            req = unquote(env['PATH_INFO'])
            if 'QUERY_STRING' in env:
                req = req + '?' + unquote_plus(env['QUERY_STRING'])
            client = env.get('HTTP_X_CLUSTER_CLIENT_IP')
            if not client and 'HTTP_X_FORWARDED_FOR' in env:
                client = env['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
            if not client:
                client = env.get('REMOTE_ADDR')
            headers = None
            if self.log_headers:
                headers = '\n'.join(
                    '%s:%s' % (h[5:].replace('_', '-').title(), v)
                    for h, v in env.items() if h.startswith('HTTP_'))
            code = status.split(' ', 1)[0]
            if env.get('brim._client_disconnect', False):
                code = HTTP_CLIENT_DISCONNECT
            try:
                code = int(code)
            except ValueError:
                code = 0
            stats.incr('status_%d_count' % code)
            xx = code // 100
            if xx == 2:
                stats.incr('status_2xx_count')
            elif xx == 3:
                stats.incr('status_3xx_count')
            elif xx == 4:
                stats.incr('status_4xx_count')
            elif xx == 5:
                stats.incr('status_5xx_count')
            log_items = [client,
                         env.get('REMOTE_ADDR'),
                         env.get('HTTP_X_AUTH_TOKEN'),
                         env.get('REMOTE_USER'),
                         strftime('%Y%m%dT%H%M%SZ', gmtime()),
                         env['REQUEST_METHOD'],
                         req,
                         env['SERVER_PROTOCOL'],
                         code,
                         env['brim._bytes_out'],
                         env['brim._bytes_in'],
                         env.get('HTTP_REFERER'),
                         env.get('HTTP_USER_AGENT'),
                         env['brim.txn'],
                         '%.5f' % (time() - env['brim.start'])]
            additional_info = env.get('brim.additional_request_log_info')
            if additional_info:
                log_items.extend(additional_info)
            if headers:
                log_items.extend(['headers:', headers])
            self.logger.notice(' '.join(_log_quote(str(x or '-'))
                                        for x in log_items))
        except Exception:
            self.logger.exception('WSGI EXCEPTION:')
        finally:
            self.logger.txn = None

    def _capture_exception(self, *excinfo):
        """
        Used by capture_exceptions_stdout_stderr to catch any
        completely uncaught exceptions and redirect them to the
        logger.
        """
        self.logger.error('UNCAUGHT EXCEPTION: wid:%03d %s' %
                          (self.worker_id, sysloggable_excinfo(*excinfo)))

    def _capture_stdout(self, value):
        """
        Used by capture_exceptions_stdout_stderr to catch anything
        sent to standard output and redirect it to the logger.
        """
        for line in value.split('\n'):
            if line:
                self.logger.info('STDOUT: wid:%03d %s' %
                                 (self.worker_id, line))

    def _capture_stderr(self, value):
        """
        Used by capture_exceptions_stdout_stderr to catch anything
        sent to standard error and redirect it to the logger.
        """
        for line in value.split('\n'):
            if line:
                self.logger.error('STDERR: wid:%03d %s' %
                                  (self.worker_id, line))


class TCPSubserver(IPSubserver):
    """
    Created for each [tcp], [tcp2], [tcp3] config section to hold the
    attributes specific to that subconfig.

    :param server: The parent brim.server.Server.
    :param name: The name of the subserver ('tcp', 'tcp2', 'tcp3',
                 etc.)
    """

    def __init__(self, server, name):
        IPSubserver.__init__(self, server, name)
        self.stats_conf.update({'connection_count': 'sum'})

    def _parse_conf(self, conf):
        IPSubserver._parse_conf(self, conf)
        call = conf.get(self.name, 'call')
        if not call:
            raise Exception(
                "[%s] not configured with 'call' option." % self.name)
        try:
            mod, cls = call.rsplit('.', 1)
        except ValueError:
            raise Exception(
                'Invalid call value %r for [%s].' % (call, self.name))
        try:
            self.handler = getattr(__import__(mod, fromlist=[cls]), cls)
        except (AttributeError, ImportError):
            raise Exception(
                'Could not load class %r for [%s].' % (call, self.name))
        try:
            args = len(getargspec(self.handler.__init__).args)
            if args != 3:
                raise Exception('Would not be able to instantiate %r for '
                    '[%s]. Incorrect number of args, %s, should be 3 (self, '
                    'name, parsed_conf).' % (call, self.name, args))
        except TypeError, err:
            if str(err) == 'arg is not a Python function':
                err = 'Probably not a class.'
            raise Exception(
                'Would not be able to instantiate %r for [%s]. %s' %
                (call, self.name, err))
        try:
            args = len(getargspec(self.handler.__call__).args)
            if args != 6:
                raise Exception('Would not be able to use %r for [%s]. '
                    'Incorrect number of __call__ args, %s, should be 6 '
                    '(self, subserver, stats, sock, ip, port).' %
                    (call, self.name, args))
        except TypeError, err:
            if str(err) == 'arg is not a Python function':
                err = 'Probably no __call__ method.'
            raise Exception('Would not be able to use %r for [%s]. %s' %
                            (call, self.name, err))
        if hasattr(self.handler, 'parse_conf'):
            try:
                args = len(getargspec(self.handler.parse_conf).args)
                if args != 3:
                    raise Exception('Cannot use %r for [%s]. Incorrect number '
                        'of parse_conf args, %s, should be 3 (cls, name, '
                        'conf).' % (call, self.name, args))
            except TypeError, err:
                if str(err) == 'arg is not a Python function':
                    err = 'parse_conf probably not a method.'
                raise Exception('Cannot use %r for [%s]. %s' %
                                (call, self.name, err))
            self.handler_conf = self.handler.parse_conf(self.name, conf)
        else:
            self.handler_conf = conf
        if hasattr(self.handler, 'stats_conf'):
            try:
                args = len(getargspec(self.handler.stats_conf).args)
                if args != 3:
                    raise Exception('Cannot use %r for [%s]. Incorrect number '
                        'of stats_conf args, %s, should be 3 (cls, name, '
                        'conf).' % (call, self.name, args))
            except TypeError, err:
                if str(err) == 'arg is not a Python function':
                    err = 'stats_conf probably not a method.'
                raise Exception('Cannot use %r for [%s]. %s' %
                                (call, self.name, err))
            for stat_name, stat_type in \
                    self.handler.stats_conf(self.name, self.handler_conf):
                self.stats_conf[stat_name] = stat_type

    def _privileged_start(self):
        try:
            self.sock = get_listening_tcp_socket(self.ip, self.port,
                backlog=self.backlog, retry=self.listen_retry,
                certfile=self.certfile, keyfile=self.keyfile, style='eventlet')
        except socket_error, err:
                raise Exception(
                    'Could not bind to %s:%s: %s' % (self.ip, self.port, err))

    def _start(self, bucket_stats):
        IPSubserver._start(self, bucket_stats)
        self.worker_id = -1
        if not self.server.output:
            capture_exceptions_stdout_stderr(
                exceptions=self._capture_exception,
                stdout_func=self._capture_stdout,
                stderr_func=self._capture_stderr)
        self.start_time = int(time())
        self.logger = get_logger(self.name, self.log_name, self.log_level,
                                 self.log_facility, self.server.no_daemon)
        self.handler = self.handler(self.name, self.handler_conf)
        sustain_workers(self.worker_count, self._tcp_worker,
                        logger=self.logger)
        if self.worker_id == -1:
            shutdown_safe(self.sock)
            self.sock.close()

    def _tcp_worker(self, worker_id):
        """
        This method is called for each TCP worker subprocess spawned
        and it simply constructs the configured handler and then
        begins sending incoming connections to it.
        """
        if setproctitle:
            if not self.server.no_daemon:
                setproctitle('%d:%s:brimd' % (worker_id, self.name))
        self.worker_id = worker_id
        self.bucket_stats.set(worker_id, 'start_time', time())
        if not self.server.no_daemon:
            use_hub(self.eventlet_hub)
        stats = _Stats(self.bucket_stats, self.worker_id)
        pool = GreenPool(size=self.concurrent_per_worker)
        try:
            while True:
                sock, (ip, port) = self.sock.accept()
                stats.incr('connection_count')
                pool.spawn_n(self.handler, self, stats, sock, ip, port)
        except socket_error, err:
            if err.errno != EINVAL:
                raise
        pool.waitall()

    def _capture_exception(self, *excinfo):
        """
        Used by capture_exceptions_stdout_stderr to catch any
        completely uncaught exceptions and redirect them to the
        logger.
        """
        self.logger.error('UNCAUGHT EXCEPTION: tid:%03d %s' %
                          (self.worker_id, sysloggable_excinfo(*excinfo)))

    def _capture_stdout(self, value):
        """
        Used by capture_exceptions_stdout_stderr to catch anything
        sent to standard output and redirect it to the logger.
        """
        for line in value.split('\n'):
            if line:
                self.logger.info('STDOUT: tid:%03d %s' %
                                 (self.worker_id, line))

    def _capture_stderr(self, value):
        """
        Used by capture_exceptions_stdout_stderr to catch anything
        sent to standard error and redirect it to the logger.
        """
        for line in value.split('\n'):
            if line:
                self.logger.error('STDERR: tid:%03d %s' %
                                  (self.worker_id, line))


class UDPSubserver(IPSubserver):
    """
    Created for each [udp], [udp2], [udp3] config section to hold the
    attributes specific to that subconfig.

    :param server: The parent brim.server.Server.
    :param name: The name of the subserver ('udp', 'udp2', 'udp3',
                 etc.)
    """

    def __init__(self, server, name):
        IPSubserver.__init__(self, server, name)
        self.stats_conf.update({'datagram_count': 'worker'})

    def _parse_conf(self, conf):
        IPSubserver._parse_conf(self, conf)
        self.worker_count = 1
        self.worker_names = ['0']
        self.max_datagram_size = conf.get_int(self.name, 'max_datagram_size',
            conf.get_int('brim', 'max_datagram_size', 65536))
        call = conf.get(self.name, 'call')
        if not call:
            raise Exception(
                "[%s] not configured with 'call' option." % self.name)
        try:
            mod, cls = call.rsplit('.', 1)
        except ValueError:
            raise Exception(
                'Invalid call value %r for [%s].' % (call, self.name))
        try:
            self.handler = getattr(__import__(mod, fromlist=[cls]), cls)
        except (AttributeError, ImportError):
            raise Exception(
                'Could not load class %r for [%s].' % (call, self.name))
        try:
            args = len(getargspec(self.handler.__init__).args)
            if args != 3:
                raise Exception('Would not be able to instantiate %r for '
                    '[%s]. Incorrect number of args, %s, should be 3 (self, '
                    'name, parsed_conf).' % (call, self.name, args))
        except TypeError, err:
            if str(err) == 'arg is not a Python function':
                err = 'Probably not a class.'
            raise Exception(
                'Would not be able to instantiate %r for [%s]. %s' %
                (call, self.name, err))
        try:
            args = len(getargspec(self.handler.__call__).args)
            if args != 7:
                raise Exception('Would not be able to use %r for [%s]. '
                    'Incorrect number of __call__ args, %s, should be 7 '
                    '(self, subserver, stats, sock, datagram, ip, port).' %
                    (call, self.name, args))
        except TypeError, err:
            if str(err) == 'arg is not a Python function':
                err = 'Probably no __call__ method.'
            raise Exception('Would not be able to use %r for [%s]. %s' %
                            (call, self.name, err))
        if hasattr(self.handler, 'parse_conf'):
            try:
                args = len(getargspec(self.handler.parse_conf).args)
                if args != 3:
                    raise Exception('Cannot use %r for [%s]. Incorrect number '
                        'of parse_conf args, %s, should be 3 (cls, name, '
                        'conf).' % (call, self.name, args))
            except TypeError, err:
                if str(err) == 'arg is not a Python function':
                    err = 'parse_conf probably not a method.'
                raise Exception('Cannot use %r for [%s]. %s' %
                                (call, self.name, err))
            self.handler_conf = self.handler.parse_conf(self.name, conf)
        else:
            self.handler_conf = conf
        if hasattr(self.handler, 'stats_conf'):
            try:
                args = len(getargspec(self.handler.stats_conf).args)
                if args != 3:
                    raise Exception('Cannot use %r for [%s]. Incorrect number '
                        'of stats_conf args, %s, should be 3 (cls, name, '
                        'conf).' % (call, self.name, args))
            except TypeError, err:
                if str(err) == 'arg is not a Python function':
                    err = 'stats_conf probably not a method.'
                raise Exception('Cannot use %r for [%s]. %s' %
                                (call, self.name, err))
            for stat_name in self.handler.stats_conf(self.name,
                                                     self.handler_conf):
                self.stats_conf[stat_name] = 'worker'

    def _privileged_start(self):
        try:
            self.sock = get_listening_udp_socket(self.ip, self.port,
                retry=self.listen_retry, style='eventlet')
        except socket_error, err:
                raise Exception(
                    'Could not bind to %s:%s: %s' % (self.ip, self.port, err))

    def _start(self, bucket_stats):
        IPSubserver._start(self, bucket_stats)
        self.worker_id = 0
        if not self.server.output:
            capture_exceptions_stdout_stderr(
                exceptions=self._capture_exception,
                stdout_func=self._capture_stdout,
                stderr_func=self._capture_stderr)
        self.start_time = int(time())
        self.logger = get_logger(self.name, self.log_name, self.log_level,
                                 self.log_facility, self.server.no_daemon)
        self.handler = self.handler(self.name, self.handler_conf)
        self.bucket_stats.set(self.worker_id, 'start_time', self.start_time)
        if not self.server.no_daemon:
            use_hub(self.eventlet_hub)
        stats = _Stats(self.bucket_stats, self.worker_id)
        pool = GreenPool(size=self.concurrent_per_worker)
        try:
            while True:
                datagram, (ip, port) = \
                    self.sock.recvfrom(self.max_datagram_size)
                stats.incr('datagram_count')
                pool.spawn_n(self.handler, self, stats, self.sock, datagram,
                             ip, port)
        except socket_error, err:
            if err.errno != EINVAL:
                raise
        pool.waitall()

    def _capture_exception(self, *excinfo):
        """
        Used by capture_exceptions_stdout_stderr to catch any
        completely uncaught exceptions and redirect them to the
        logger.
        """
        self.logger.error('UNCAUGHT EXCEPTION: uid:%03d %s' %
                          (self.worker_id, sysloggable_excinfo(*excinfo)))

    def _capture_stdout(self, value):
        """
        Used by capture_exceptions_stdout_stderr to catch anything
        sent to standard output and redirect it to the logger.
        """
        for line in value.split('\n'):
            if line:
                self.logger.info('STDOUT: uid:%03d %s' %
                                 (self.worker_id, line))

    def _capture_stderr(self, value):
        """
        Used by capture_exceptions_stdout_stderr to catch anything
        sent to standard error and redirect it to the logger.
        """
        for line in value.split('\n'):
            if line:
                self.logger.error('STDERR: uid:%03d %s' %
                                  (self.worker_id, line))


class DaemonsSubserver(Subserver):
    """
    Created for a [daemons] config section to hold the attributes
    specific to that subconfig.

    :param server: The parent brim.server.Server.
    """

    def __init__(self, server, name='daemons'):
        Subserver.__init__(self, server, name)

    def _parse_conf(self, conf):
        Subserver._parse_conf(self, conf)
        self.daemons = []
        daemon_names = conf.get(self.name, 'daemons', '').strip().split()
        for daemon_name in daemon_names:
            call = conf.get(daemon_name, 'call')
            if not call:
                raise Exception(
                    "Daemon [%s] not configured with 'call' option." %
                    daemon_name)
            try:
                mod, cls = call.rsplit('.', 1)
            except ValueError:
                raise Exception(
                    'Invalid call value %r for daemon [%s].' %
                    (call, daemon_name))
            try:
                daemon_class = getattr(__import__(mod, fromlist=[cls]), cls)
            except (AttributeError, ImportError):
                raise Exception('Could not load class %r for daemon [%s].' %
                                (call, daemon_name))
            try:
                args = len(getargspec(daemon_class.__init__).args)
                if args != 3:
                    raise Exception('Would not be able to instantiate %r for '
                        'daemon [%s]. Incorrect number of args, %s, should be '
                        '3 (self, name, conf).' % (call, daemon_name, args))
            except TypeError, err:
                if str(err) == 'arg is not a Python function':
                    err = 'Probably not a class.'
                raise Exception(
                    'Would not be able to instantiate %r for daemon [%s]. %s' %
                    (call, daemon_name, err))
            try:
                args = len(getargspec(daemon_class.__call__).args)
                if args != 3:
                    raise Exception('Would not be able to use %r for daemon '
                        '[%s]. Incorrect number of __call__ args, %s, should '
                        'be 3 (self, subserver, stats).' %
                        (call, daemon_name, args))
            except TypeError, err:
                if str(err) == 'arg is not a Python function':
                    err = 'Probably no __call__ method.'
                raise Exception(
                    'Would not be able to use %r for daemon [%s]. %s' %
                    (call, daemon_name, err))
            if hasattr(daemon_class, 'parse_conf'):
                try:
                    args = len(getargspec(daemon_class.parse_conf).args)
                    if args != 3:
                        raise Exception('Cannot use %r for daemon [%s]. '
                            'Incorrect number of parse_conf args, %s, should '
                            'be 3 (cls, name, conf).' %
                            (call, daemon_name, args))
                except TypeError, err:
                    if str(err) == 'arg is not a Python function':
                        err = 'parse_conf probably not a method.'
                    raise Exception('Cannot use %r for daemon [%s]. %s' %
                                    (call, daemon_name, err))
                daemon_conf = daemon_class.parse_conf(daemon_name, conf)
            else:
                daemon_conf = conf
            if hasattr(daemon_class, 'stats_conf'):
                try:
                    args = len(getargspec(daemon_class.stats_conf).args)
                    if args != 3:
                        raise Exception('Cannot use %r for daemon [%s]. '
                            'Incorrect number of stats_conf args, %s, should '
                            'be 3 (cls, name, conf).' %
                            (call, daemon_name, args))
                except TypeError, err:
                    if str(err) == 'arg is not a Python function':
                        err = 'stats_conf probably not a method.'
                    raise Exception('Cannot use %r for daemon [%s]. %s' %
                                    (call, daemon_name, err))
                for stat_name in \
                        daemon_class.stats_conf(daemon_name, daemon_conf):
                    self.stats_conf[stat_name] = 'worker'
            self.daemons.append((daemon_name, daemon_class, daemon_conf))
        self.worker_count = len(self.daemons)
        self.worker_names = [d[0] for d in self.daemons]
        if not self.worker_names:
            self.worker_names = ['0']

    def _start(self, bucket_stats):
        Subserver._start(self, bucket_stats)
        self.worker_id = -1
        if not self.server.output:
            capture_exceptions_stdout_stderr(
                exceptions=self._capture_exception,
                stdout_func=self._capture_stdout,
                stderr_func=self._capture_stderr)
        self.start_time = int(time())
        self.logger = get_logger(self.name, self.log_name, self.log_level,
                                 self.log_facility, self.server.no_daemon)
        sustain_workers(self.worker_count, self._daemon,
                        logger=self.logger)

    def _daemon(self, worker_id):
        """
        This method is called for each daemon subprocess spawned and
        it simply constructs and starts the corresponding daemon.
        """
        name, cls, conf = self.daemons[worker_id]
        if setproctitle:
            setproctitle('%s:%s:brimd' % (name, self.name))
        self.worker_id = worker_id
        stats = _Stats(self.bucket_stats, worker_id)
        stats.set('start_time', time())
        daemon = cls(name, conf)
        daemon(self, stats)
        return daemon  # Really done just for unit testing

    def _capture_exception(self, *excinfo):
        """
        Used by capture_exceptions_stdout_stderr to catch any
        completely uncaught exceptions and redirect them to the
        logger.
        """
        self.logger.error('UNCAUGHT EXCEPTION: did:%03d %s' %
                          (self.worker_id, sysloggable_excinfo(*excinfo)))

    def _capture_stdout(self, value):
        """
        Used by capture_exceptions_stdout_stderr to catch anything
        sent to standard output and redirect it to the logger.
        """
        for line in value.split('\n'):
            if line:
                self.logger.info('STDOUT: did:%03d %s' %
                                 (self.worker_id, line))

    def _capture_stderr(self, value):
        """
        Used by capture_exceptions_stdout_stderr to catch anything
        sent to standard error and redirect it to the logger.
        """
        for line in value.split('\n'):
            if line:
                self.logger.error('STDERR: did:%03d %s' %
                                  (self.worker_id, line))


class Server(object):
    """
    The main class for the Brim.Net Core Server launched by the brimd
    script. Few daemons or apps need to access this directly.

    :param args: Command line arguments for the server, without the
                 process name. Defaults to sys.argv[1:]
    :param stdin: The file-like object to treat as standard input.
                  Defaults to sys.stdin.
    :param stdout: The file-like object to treat as standard output.
                   Defaults to sys.stdout.
    :param stderr: The file-like object to treat as standard error.
                   Defaults to sys.stderr.
    """

    def __init__(self, args=None, stdin=None, stdout=None, stderr=None):
        self.args = args
        if self.args is None:
            self.args = sys_argv[1:]
        self.stdin = stdin
        if self.stdin is None:
            self.stdin = sys_stdin
        self.stdout = stdout
        if self.stdout is None:
            self.stdout = sys_stdout
        self.stderr = stderr
        if self.stderr is None:
            self.stderr = sys_stderr
        self.subservers = []

    def main(self):
        """
        Performs the brimd actions (start, stop, restart, shutdown,
        etc.) determined by the command line arguments given in the
        constructor. Usage can be read from ``brimd --help``.

        :returns: An integer exit code suitable for returning with
                  sys.exit.
        """
        try:
            conf = self._parse_args()
            if not conf:
                return 0
            self._parse_conf(conf)
            self._start()
            return 0
        except Exception, err:
            self.stderr.write('%s\n' % err)
            self.stderr.flush()
            return 1

    def _parse_args(self):
        """
        This is where the translation and initial reaction to the
        command line is done.

        :returns: None if no further action is necessary or a
                  brim.conf.Conf instance if the server should be
                  started.
        """
        parser = OptionParser(add_help_option=False, usage="""
Usage: %%prog [options] [command]

Brim.Net Core Server %s

Command (defaults to 'no-daemon'):

  start                 Starts brimd if it isn't already running.
  restart               Starts a new brimd which will wait for any previously
                        existing one to release the listening port(s) and then
                        tells any previously existing brimd to shutdown.
  shutdown              Immediately releases the listening port(s) and the main
                        process exits. Any subprocesses will continue to serve
                        any existing connections and then exit once those
                        connections close.
  stop                  Terminates brimd immediately, severing any existing
                        connections and therefore any in-progress requests.
  status                Displays whether brimd is currently running or not.
  reload                Same as restart.
  force-reload          Same as restart.
  no-daemon             Starts the server in the foreground with no
                        subprocesses, PID files are ignored and not created,
                        and output will go to stdout and stderr. Note that only
                        core apps will be started and no daemons. This can
                        be useful for debugging.
            """.strip() % brim.version)
        parser.add_option('-?', '-h', '--help', dest='help',
            action='store_true', default=False,
            help='Outputs this help information.')
        parser.add_option('-c', '--conf', action='append', dest='conf_files',
            metavar='PATH',
            help='By default, /etc/brimd.conf and ~/.brimd.conf are read for '
                 'configuration. You may override this by specifying a '
                 'specific conf file with -c. This option may be specified '
                 'more than once and the conf files will each be read in '
                 'order.')
        parser.add_option('-p', '--pid-file', dest='pid_file',
            default='/var/run/brimd.pid', metavar='PATH',
            help='The path to the file to store the PID of the running main '
                 'brimd process.')
        parser.add_option('-o', '--output', dest='output',
            action='store_true', default=False,
            help='When running as a daemon brimd will normally close '
                 'standard input, output, and error; this option will leave '
                 'them open, which can be useful for debugging.')
        parser.add_option('-v', '--version', dest='version',
            action='store_true', default=False,
            help='Displays the version of brimd.')

        def _parser_error(msg):
            raise Exception(msg)

        parser.error = _parser_error
        options, args = parser.parse_args(self.args)
        if options.help:
            parser.print_help(self.stdout)
            return 0
        if len(args) > 1:
            raise Exception('Too many commands given; only one allowed.')
        if options.version:
            print >>self.stdout, 'Brim.Net Core Server', brim.version
            return 0
        if not options.conf_files:
            options.conf_files = DEFAULT_CONF_FILES
        self.pid_file = options.pid_file
        command = args[0] if args else 'no-daemon'
        self.no_daemon = command == 'no-daemon'
        self.output = options.output or self.no_daemon
        if command == 'start':
            success, pid = _send_pid_sig(self.pid_file, 0)
            if success:
                print >>self.stdout, '%s already running' % pid
            else:
                conf = read_conf(options.conf_files)
                if not conf.files:
                    raise Exception('No configuration found.')
                return conf
        elif command in ('restart', 'reload', 'force-reload'):
            conf = read_conf(options.conf_files)
            if not conf.files:
                raise Exception('No configuration found.')
            success, pid = _send_pid_sig(self.pid_file, 0)
            # If brimd is already running, we fork a child to shut it down
            # after a second so we, as the new brimd, can grab the port.
            if success and not fork():
                sleep(1)
                _send_pid_sig(self.pid_file, SIGHUP, expect_exit=True,
                              pid_override=pid)
                return None
            else:
                return conf
        elif command == 'shutdown':
            _send_pid_sig(self.pid_file, SIGHUP, expect_exit=True)
        elif command == 'stop':
            _send_pid_sig(self.pid_file, SIGTERM, expect_exit=True)
        elif command == 'status':
            success, pid = _send_pid_sig(self.pid_file, 0)
            if success:
                print >>self.stdout, '%s is running' % pid
            elif pid:
                print >>self.stdout, '%s is not running' % pid
            else:
                print >>self.stdout, 'not running'
        elif command == 'no-daemon':
            conf = read_conf(options.conf_files)
            if not conf.files:
                raise Exception('No configuration found.')
            return conf
        else:
            raise Exception('Unknown command %r.' % command)
        return None

    def _parse_conf(self, conf):
        """
        Translates the brim.conf.Conf configuration into instance
        attributes for use later. This ensures we have a good
        configuration before we try starting the server.

        :param conf: The brim.conf.Conf instance for the overall
                     server configuration.
        """

        def _conf_error(section, option, value, conversion_type, err):
            raise Exception('Configuration value [%s] %s of %r cannot be '
                            'converted to %s.' %
                            (section, option, value, conversion_type))

        conf.error = _conf_error
        self.user = conf.get('brim', 'user')
        self.group = conf.get('brim', 'group')
        self.umask = conf.get('brim', 'umask', '0022')
        try:
            self.umask = int(self.umask, 8)
        except ValueError:
            raise Exception('Invalid umask value %r.' % self.umask)

        self.log_name = conf.get('brim', 'log_name', 'brim')
        self.log_level = conf.get('brim', 'log_level', 'INFO').upper()
        try:
            import logging
            getattr(logging, self.log_level)
        except AttributeError:
            raise Exception(
                'Invalid [brim] log_level %r.' % (self.log_level,))
        self.log_facility = conf.get('brim', 'log_facility', 'LOCAL0').upper()
        if not self.log_facility.startswith('LOG_'):
            self.log_facility = 'LOG_' + self.log_facility
        try:
            from logging.handlers import SysLogHandler
            getattr(SysLogHandler, self.log_facility)
        except AttributeError:
            raise Exception('Invalid [brim] log_facility %r.' %
                            (self.log_facility,))

        for key in conf.store.keys():
            if key == 'wsgi' or key.startswith('wsgi') and key[4:].isdigit():
                self.subservers.append(WSGISubserver(self, key))
            elif key == 'tcp' or key.startswith('tcp') and key[3:].isdigit():
                self.subservers.append(TCPSubserver(self, key))
            elif key == 'udp' or key.startswith('udp') and key[3:].isdigit():
                self.subservers.append(UDPSubserver(self, key))
            elif key == 'daemons' and not self.no_daemon:
                self.subservers.append(DaemonsSubserver(self))
        for subserver in self.subservers:
            subserver._parse_conf(conf)

    def _start(self):
        """
        This is the last method run by the main brimd server process.
        It calls the subservers' ``_privileged_start`` methods (to
        bind the listening sockets, for example), drops privileges,
        daemonizes if enabled (and updates the pid file), configures
        a default logger, and then calls the subservers' ``_start``
        methods.
        """
        if not self.subservers:
            raise Exception('No subservers configured.')
        for subserver in self.subservers:
            subserver._privileged_start()
        if not self.no_daemon:
            pid = fork()
            if pid:
                with open(self.pid_file, 'w') as pid_file:
                    pid_file.write('%s\n' % pid)
                return 0
        if not self.output:
            capture_exceptions_stdout_stderr(
                exceptions=self._capture_exception,
                stdout_func=self._capture_stdout,
                stderr_func=self._capture_stderr)
        droppriv(self.user, self.group, self.umask)
        self.start_time = int(time())
        self.logger = get_logger('brim', self.log_name, self.log_level,
                                 self.log_facility, self.no_daemon)
        self.bucket_stats = []
        for subserver in self.subservers:
            self.bucket_stats.append(_BucketStats(
                subserver.worker_names, subserver.stats_conf))
        if self.no_daemon:
            if setproctitle:
                setproctitle('brimd')
            use_hub(self.subservers[0].eventlet_hub)
            pool = GreenPool()
            coros = []
            for index, subserver in enumerate(self.subservers):
                coros.append(pool.spawn(
                    subserver._start, self.bucket_stats[index]))
            pool.waitall()
            retval = max(c.wait() for c in coros)
            return retval
        else:
            if setproctitle:
                setproctitle('main:brimd')
            sustain_workers(len(self.subservers), self._start_subserver,
                            logger=self.logger)

    def _start_subserver(self, index):
        subserver = self.subservers[index]
        if setproctitle:
            setproctitle('%s:brimd' % subserver.name)
        return subserver._start(self.bucket_stats[index])

    def _capture_exception(self, *excinfo):
        """
        Used by capture_exceptions_stdout_stderr to catch any
        completely uncaught exceptions and redirect them to the
        logger.
        """
        self.logger.error(
            'UNCAUGHT EXCEPTION: main %s' % (sysloggable_excinfo(*excinfo),))

    def _capture_stdout(self, value):
        """
        Used by capture_exceptions_stdout_stderr to catch anything
        sent to standard output and redirect it to the logger.
        """
        for line in value.split('\n'):
            if line:
                self.logger.info('STDOUT: main %s' % (line,))

    def _capture_stderr(self, value):
        """
        Used by capture_exceptions_stdout_stderr to catch anything
        sent to standard error and redirect it to the logger.
        """
        for line in value.split('\n'):
            if line:
                self.logger.error('STDERR: main %s' % (line,))
