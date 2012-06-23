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

from logging.handlers import SysLogHandler
from logging import DEBUG, getLogger, INFO, StreamHandler
from StringIO import StringIO
from sys import stdout
from unittest import main, TestCase

from brim import log


class FakeLogger(object):

    def __init__(self):
        self.error_calls = []
        self.log_calls = []

    def getEffectiveLevel(self):
        return DEBUG

    def error(self, *args, **kwargs):
        self.error_calls.append((args, kwargs))

    def log(self, level, msg, *args, **kwargs):
        self.log_calls.append((level, msg, args, kwargs))


class TestLogAdapter(TestCase):

    def test_process(self):
        a = log._LogAdapter(None, 'testserver')
        a.txn = 'abc'
        self.assertEquals(a.process('test', {}), (
            'test', {'extra': {'txn': 'abc', 'server': 'testserver'}}))

    def test_effective_level(self):
        a = log._LogAdapter(FakeLogger(), 'testserver')
        self.assertEquals(a.getEffectiveLevel(), DEBUG)

    def test_exception(self):
        logger = FakeLogger()
        a = log._LogAdapter(logger, 'testserver')
        a.exception('testexc')
        self.assertEquals(logger.error_calls, [(
            ("testexc None ['None']",),
            {'extra': {'txn': None, 'server': 'testserver'}})])
        try:
            raise Exception('blah')
        except Exception:
            a.exception('testexc2')
        self.assertEquals(len(logger.error_calls), 2)
        self.assertEquals(
            logger.error_calls[-1][1],
            {'extra': {'txn': None, 'server': 'testserver'}})
        self.assertTrue(logger.error_calls[-1][0][0].startswith(
            'testexc2 Exception: blah [\'Traceback (most recent call '
            'last):\', \'  File '))
        self.assertTrue(logger.error_calls[-1][0][0].endswith(
            ', in test_exception\', "    raise Exception(\'blah\')", '
            '\'Exception: blah\']'))

    def test_notice(self):
        logger = FakeLogger()
        a = log._LogAdapter(logger, 'testserver')
        a.notice('testnotice')
        self.assertEquals(logger.log_calls, [(
            log.NOTICE, 'testnotice', (),
            {'extra': {'txn': None, 'server': 'testserver'}})])


class FakeRecord(object):

    def __init__(self):
        self.txn = 'def'
        self.levelno = DEBUG
        self.server = 'testserver'
        self.exc_info = None
        self.exc_text = 'testexc'

    def getMessage(self):
        return 'recordmessage'


class TestLogFormatter(TestCase):

    def test_format(self):
        f = log._LogFormatter()
        self.assertEquals(f.format(FakeRecord()),
                          'testserver recordmessage\ntestexc txn:def')


class TestSysloggableExcInfo(TestCase):

    def test_sysloggable_excinfo(self):
        self.assertEquals(log.sysloggable_excinfo(), "None ['None']")
        try:
            raise Exception('test')
        except:
            sei = log.sysloggable_excinfo()
            self.assertTrue(sei.startswith(
                'Exception: test [\'Traceback (most recent call last):\', \'  '
                'File '))
            self.assertTrue(sei.endswith(
                ', in test_sysloggable_excinfo\', "    raise '
                'Exception(\'test\')", \'Exception: test\']'))
        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt:
            self.assertEquals(log.sysloggable_excinfo(), 'KeyboardInterrupt')


class TestGetLogger(TestCase):

    def test_get_logger(self):
        logger = log.get_logger('route', 'name', 'DEBUG', 'LOG_LOCAL0', False)
        self.assertEquals(logger.logger, getLogger('route'))
        self.assertEquals(logger.server, 'name')
        self.assertEquals(logger.getEffectiveLevel(), DEBUG)
        found = False
        for handler in logger.logger.handlers:
            if isinstance(handler, SysLogHandler):
                found = True
                break
        self.assertTrue(found)
        self.assertTrue(handler.facility, SysLogHandler.LOG_LOCAL0)

        logger = log.get_logger('route', 'name2', 'INFO', 'LOG_LOCAL1', False)
        self.assertEquals(logger.logger, getLogger('route'))
        self.assertEquals(logger.server, 'name2')
        self.assertEquals(logger.getEffectiveLevel(), INFO)
        found = False
        for handler in logger.logger.handlers:
            if isinstance(handler, SysLogHandler):
                found = True
                break
        self.assertTrue(found)
        self.assertTrue(handler.facility, SysLogHandler.LOG_LOCAL1)

    def test_get_console_logger(self):
        logger = log.get_logger('route', 'name', 'DEBUG', 'LOG_LOCAL0', True)
        self.assertEquals(logger.logger, getLogger('route'))
        self.assertEquals(logger.server, 'name')
        self.assertEquals(logger.getEffectiveLevel(), DEBUG)
        found = False
        for handler in logger.logger.handlers:
            if isinstance(handler, StreamHandler):
                found = True
                break
        self.assertTrue(found)
        self.assertTrue(handler.stream, stdout)


if __name__ == '__main__':
    main()
