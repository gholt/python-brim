"""Tests for brim.daemon_sample."""
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

from mock import call, MagicMock, patch

from brim import daemon_sample
from brim.conf import Conf


class MockStats(object):

    def __init__(self):
        self.stats = {}

    def get(self, name):
        return self.stats.get(name, 0)

    def set(self, name, value):
        self.stats[name] = value

    def incr(self, name):
        self.stats[name] = self.stats.get(name, 0) + 1


class TestDaemonSample(TestCase):

    @patch.object(daemon_sample, 'time', return_value=123)
    def test_call(self, mock_time):
        def _sleep(*args):
            _sleep.calls.append(args)
            if len(_sleep.calls) == 3:
                raise _sleep.exception
        _sleep.calls = []
        _sleep.exception = Exception()
        with patch.object(daemon_sample, 'sleep', _sleep):
            s = daemon_sample.DaemonSample('test', {'interval': 60})
            mock_server = MagicMock()
            mock_stats = MockStats()
            exc = None
            try:
                s(mock_server, mock_stats)
            except Exception as err:
                exc = err
            self.assertTrue(exc is _sleep.exception)
            self.assertEqual(_sleep.calls, [(60,)] * 3)
            mock_server.logger.info.assert_has_calls([
                call('test sample daemon log line 1'),
                call('test sample daemon log line 2'),
                call('test sample daemon log line 3')])
            self.assertEqual(mock_stats.get('last_run'), 123)
            self.assertEqual(mock_stats.get('iterations'), 3)

    def test_parse_conf(self):
        c = daemon_sample.DaemonSample.parse_conf('test', Conf({}))
        self.assertEqual(c, {'interval': 60})
        c = daemon_sample.DaemonSample.parse_conf(
            'test', Conf({'test': {'interval': 123}}))
        self.assertEqual(c, {'interval': 123})
        c = daemon_sample.DaemonSample.parse_conf(
            'test', Conf({'test2': {'interval': 123}}))
        self.assertEqual(c, {'interval': 60})

    def test_stats_conf(self):
        self.assertEqual(daemon_sample.DaemonSample.stats_conf(
            'test', {'interval': 60}),
            [('iterations', 'daemon'), ('last_run', 'daemon')])


if __name__ == '__main__':
    main()
