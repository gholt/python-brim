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

import ConfigParser
from StringIO import StringIO
from unittest import main, TestCase
from uuid import uuid4

from brim import conf


class TestConf(TestCase):

    def test_true_values(self):
        self.assertEquals(conf.TRUE_VALUES,
                          [v.lower() for v in conf.TRUE_VALUES])

    def test_false_values(self):
        self.assertEquals(conf.FALSE_VALUES,
                          [v.lower() for v in conf.FALSE_VALUES])

    def test_true_false_values_distinct(self):
        self.assertEquals(set(),
            set(conf.TRUE_VALUES).intersection(set(conf.FALSE_VALUES)))

    def test_direct_store(self):
        d = {'s1': {'o1': '1.1', 'o2': '1.2'},
             's2': {'o1': '2.1', 'o2': '2.2'}}
        self.assertEquals(d, conf.Conf(d).store)

    def test_files(self):
        f = ['one.conf', 'two.conf']
        self.assertEquals(f, conf.Conf({}, f).files)

    def test_get(self):
        self.assertEquals('1.1',
            conf.Conf({'s1': {'o1': '1.1'}}).get('s1', 'o1'))

    def test_get_default(self):
        self.assertEquals('d', conf.Conf({}).get('s1', 'o1', 'd'))

    def test_get_default_orig_is_none(self):
        self.assertEquals('d',
            conf.Conf({'s1': {'o1': None}}).get('s1', 'o1', 'd'))

    def test_get_default_orig_is_empty(self):
        self.assertEquals('d',
            conf.Conf({'s1': {'o1': ''}}).get('s1', 'o1', 'd'))

    def test_get_default_orig_is_something(self):
        self.assertEquals('s',
            conf.Conf({'s1': {'o1': 's'}}).get('s1', 'o1', 'd'))

    def test_get_bool(self):
        self.assertTrue(
            conf.Conf({'s1': {'o1': 'True'}}).get_bool('s1', 'o1', False))
        self.assertFalse(
            conf.Conf({'s1': {'o1': 'False'}}).get_bool('s1', 'o1', True))

    def test_get_bool_default(self):
        self.assertTrue(conf.Conf({}).get_bool('s1', 'o1', True))
        self.assertFalse(conf.Conf({}).get_bool('s1', 'o1', False))

    def test_get_bool_error(self):
        calls = []

        def _exit(v):
            calls.append(v)

        orig_exit = conf.exit
        try:
            conf.exit = _exit
            conf.Conf({'s1': {'o1': 'z'}}).get_bool('s1', 'o1', True)
        finally:
            conf.exit = orig_exit
        self.assertEquals(calls, ["Configuration value [s1] o1 of 'z' cannot "
                                  "be converted to boolean."])

    def test_get_int(self):
        self.assertEquals(1,
            conf.Conf({'s1': {'o1': '1'}}).get_int('s1', 'o1', -2))
        self.assertEquals(-2,
            conf.Conf({'s1': {'o1': '-2'}}).get_int('s1', 'o1', 1))

    def test_get_int_default(self):
        self.assertEquals(1, conf.Conf({}).get_int('s1', 'o1', 1))

    def test_get_int_error(self):
        calls = []

        def _exit(v):
            calls.append(v)

        orig_exit = conf.exit
        try:
            conf.exit = _exit
            conf.Conf({'s1': {'o1': 'z'}}).get_int('s1', 'o1', 1)
        finally:
            conf.exit = orig_exit
        self.assertEquals(calls,
            ["Configuration value [s1] o1 of 'z' cannot be converted to int."])

    def test_get_float(self):
        self.assertEquals(1.1,
            conf.Conf({'s1': {'o1': '1.1'}}).get_float('s1', 'o1', -2.3))
        self.assertEquals(-2.3,
            conf.Conf({'s1': {'o1': '-2.3'}}).get_float('s1', 'o1', 1.1))

    def test_get_float_default(self):
        self.assertEquals(1.1, conf.Conf({}).get_float('s1', 'o1', 1.1))

    def test_get_float_error(self):
        calls = []

        def _exit(v):
            calls.append(v)

        orig_exit = conf.exit
        try:
            conf.exit = _exit
            conf.Conf({'s1': {'o1': 'z'}}).get_float('s1', 'o1', 1.1)
        finally:
            conf.exit = orig_exit
        self.assertEquals(calls, ["Configuration value [s1] o1 of 'z' cannot "
                                  "be converted to float."])

    def test_str(self):
        d = {'s1': {'o1': '1.1', 'o2': '1.2'},
             's2': {'o1': '2.1', 'o2': '2.2'}}
        self.assertEquals("Conf based on 'unknown files': " + str(d),
                          str(conf.Conf(d)))
        f = ['one.conf', 'two.conf']
        self.assertEquals('Conf based on ' + str(f) + ': ' + str(d),
                          str(conf.Conf(d, f)))

    def test_repr(self):
        d = {'s1': {'o1': '1.1', 'o2': '1.2'},
             's2': {'o1': '2.1', 'o2': '2.2'}}
        self.assertEquals("Conf based on 'unknown files': " + str(d),
                          repr(conf.Conf(d)))
        f = ['one.conf', 'two.conf']
        self.assertEquals('Conf based on ' + str(f) + ': ' + str(d),
                          repr(conf.Conf(d, f)))

    def test_read_conf_calls_expanduser(self):
        calls = []

        def _expanduser(path):
            calls.append(path)
            return path

        u1 = uuid4().hex
        u2 = uuid4().hex
        orig_expanduser = conf.expanduser
        try:
            conf.expanduser = _expanduser
            conf.read_conf([u1, u2])
        finally:
            conf.expanduser = orig_expanduser
        self.assertEquals(calls, [u1, u2])

    def test_read_conf_exits_on_read_exception(self):
        exc = None
        calls = []

        def _exit(v):
            calls.append(v)
            raise Exception('end test')

        class _SafeConfigParser(object):

            def read(self, files):
                raise ConfigParser.Error('SafeConfigParser error')

        orig_exit = conf.exit
        orig_SafeConfigParser = conf.SafeConfigParser
        try:
            conf.exit = _exit
            conf.SafeConfigParser = _SafeConfigParser
            conf.read_conf(['test.conf'])
        except Exception, err:
            exc = err
        finally:
            conf.exit = orig_exit
            conf.SafeConfigParser = orig_SafeConfigParser
        self.assertEquals(['SafeConfigParser error'], [str(v) for v in calls])
        self.assertEquals('end test', str(exc))

    def test_read_conf_raises_read_exception_if_asked(self):
        exc = None

        class _SafeConfigParser(object):

            def read(self, files):
                raise ConfigParser.Error('SafeConfigParser error')

        orig_SafeConfigParser = conf.SafeConfigParser
        try:
            conf.SafeConfigParser = _SafeConfigParser
            conf.read_conf(['test.conf'], exit_on_read_exception=False)
        except Exception, err:
            exc = err
        finally:
            conf.SafeConfigParser = orig_SafeConfigParser
        self.assertEquals('SafeConfigParser error', str(exc))

    def test_read_conf(self):

        class _SafeConfigParser(ConfigParser.SafeConfigParser):

            def read(self, files):
                ConfigParser.SafeConfigParser.readfp(self, StringIO('''
[DEFAULT]
default1 = 1

[section1]
option1 = 1.1
option2 = 1.2

[section2]
option1 = 2.1
option2 = 2.2
                '''))
                return files

        orig_SafeConfigParser = conf.SafeConfigParser
        try:
            conf.SafeConfigParser = _SafeConfigParser
            c = conf.read_conf(['test1.conf', 'test2.conf'],
                               exit_on_read_exception=False)
            self.assertEquals(c.store,
                {'section1': {'default1': '1', 'option1': '1.1',
                              'option2': '1.2'},
                 'section2': {'default1': '1', 'option1': '2.1',
                              'option2': '2.2'}})
            self.assertEquals(c.files, ['test1.conf', 'test2.conf'])
        finally:
            conf.SafeConfigParser = orig_SafeConfigParser

    def test_read_conf_stops_after_50(self):

        class _SafeConfigParser(ConfigParser.SafeConfigParser):

            def read(self, files):
                ConfigParser.SafeConfigParser.readfp(self, StringIO('''
[brim]
additional_confs = same_file
                '''))
                return files

        exc = None
        orig_SafeConfigParser = conf.SafeConfigParser
        try:
            conf.SafeConfigParser = _SafeConfigParser
            conf.read_conf(['test.conf'], exit_on_read_exception=False)
        except Exception, err:
            exc = err
        finally:
            conf.SafeConfigParser = orig_SafeConfigParser
        self.assertTrue(str(exc).startswith(
            'Tried to read more than 50 conf files.\n'
            'Recursion with [brim_conf] additional_confs?\n'
            'Files read so far: '))

    def test_read_conf_stops_after_50_with_exit(self):
        exc = None
        calls = []

        def _exit(v):
            calls.append(v)
            raise Exception('end test')

        class _SafeConfigParser(ConfigParser.SafeConfigParser):

            def read(self, files):
                ConfigParser.SafeConfigParser.readfp(self, StringIO('''
[brim]
additional_confs = same_file
                '''))
                return files

        orig_exit = conf.exit
        orig_SafeConfigParser = conf.SafeConfigParser
        try:
            conf.exit = _exit
            conf.SafeConfigParser = _SafeConfigParser
            conf.read_conf(['test.conf'])
        except Exception, err:
            exc = err
        finally:
            conf.exit = orig_exit
            conf.SafeConfigParser = orig_SafeConfigParser
        self.assertEquals(str(exc), 'end test')
        self.assertEquals(len(calls), 1)
        self.assertTrue(str(calls[0]).startswith(
            'Tried to read more than 50 conf files.\n'
            'Recursion with [brim_conf] additional_confs?\n'
            'Files read so far: '))


if __name__ == '__main__':
    main()
