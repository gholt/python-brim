"""Provides logging utilities for brimd.

Normally you don't need to use this module directly as the active logger
itself is passed via the WSGI ``env['brim.logger']`` value.
"""
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

__all__ = ['get_logger', 'NOTICE', 'sysloggable_excinfo']

import logging
from eventlet.green import thread, threading
from logging import StreamHandler
from logging.handlers import SysLogHandler
from sys import exc_info, stdout
from traceback import format_exception

# Patch up logging to support Eventlet coroutines.
logging.thread = thread
logging.threading = threading
logging._lock = logging.threading.RLock()
NOTICE = 25
"""An additional log level patched into the standard logging levels.

This level is to be used for logging HTTP requests only so that it can
be easily filtered on to form access logs.
"""
logging.NOTICE = NOTICE
logging._levelNames[NOTICE] = 'NOTICE'
SysLogHandler.priority_map['NOTICE'] = 'notice'


class _LogAdapter(logging.LoggerAdapter, object):
    """Extended LoggerAdapter for txn and server values and notice.

    Provides support for the thread/coroutine-local ``txn`` attribute,
    passing of the server name and txn attribute with each log record,
    and providing an additional :py:func:`notice()` method for the new
    :py:attr:`NOTICE` log level.
    """

    _cls_thread_local = threading.local()

    def __init__(self, logger, server):
        logging.LoggerAdapter.__init__(self, logger, {})
        self.server = server

    @property
    def txn(self):
        if hasattr(self._cls_thread_local, 'txn'):
            return self._cls_thread_local.txn

    @txn.setter
    def txn(self, value):
        self._cls_thread_local.txn = value

    def getEffectiveLevel(self):
        return self.logger.getEffectiveLevel()

    def process(self, msg, kwargs):
        kwargs['extra'] = {'server': self.server, 'txn': self.txn}
        return msg, kwargs

    def exception(self, msg, *args, **kwargs):
        self.error('%s %s' % (msg, sysloggable_excinfo()))

    def notice(self, msg, *args, **kwargs):
        self.log(NOTICE, msg, *args, **kwargs)


class _LogFormatter(logging.Formatter):
    """Extended Formatter for txn and server values.

    Always emits the server name and ensures the txn (if set) is in the
    log line somewhere.
    """

    def __init__(self):
        logging.Formatter.__init__(self, '%(server)s %(message)s')

    def format(self, record):
        msg = logging.Formatter.format(self, record).strip()
        if record.txn and record.txn not in msg:
            msg = '%s txn:%s' % (msg, record.txn)
        return msg


def sysloggable_excinfo(*excinfo):
    """Returns exception information as a string for syslog.

    The returned string will have no newlines, the exception type and
    message first in case the line is truncated, and anything else
    deemed to make it nicer for delivery to syslog.

    :param excinfo: The exception info (exctype, value, traceback) such
        as returned with sys.exc_info.
    """
    if not excinfo:
        excinfo = exc_info()
    if excinfo[0] == KeyboardInterrupt:
        return 'KeyboardInterrupt'
    lines = ''.join(format_exception(*excinfo)).strip().split('\n')
    return '%s %r' % (lines[-1], lines)


def get_logger(route, name, level, facility='LOG_USER', console=False):
    """Returns a Logger based on the information given.

    :param route: The str log route, which is often the same as the name
        but does not have to be. Think of this as the key for the logger
        in source code.
    :param name: The str log name, this is the name sent to the
        underlying log system. Think of this as the display name for the
        logger.
    :param level: The str log level for which any records at or above
        the level will be sent to the underlying log system. Any records
        below the level will be discarded.
    :param facility: If the underlying log system supports it, such as
        syslog, this str facility value can help direct the system where
        to store the records.
    :param console: If set True, the underlying log system will simply
        be to sys.stdout. This can be useful for debugging. Normally
        you'll want to set this False so the log records are sent to
        syslog.
    """
    logger = logging.getLogger(route)
    logger.propagate = False
    if not hasattr(get_logger, 'handler2logger'):
        get_logger.handler2logger = {}
    if logger in get_logger.handler2logger:
        logger.removeHandler(get_logger.handler2logger[logger])
    if console:
        handler = StreamHandler(stdout)
    else:
        facility = getattr(SysLogHandler, facility)
        handler = SysLogHandler(address='/dev/log', facility=facility)
    handler.setFormatter(_LogFormatter())
    logger.addHandler(handler)
    get_logger.handler2logger[logger] = handler
    logger.setLevel(getattr(logging, level.upper()))
    return _LogAdapter(logger, name)
