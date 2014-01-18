"""Tests for brim.conf."""
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
from ConfigParser import Error, SafeConfigParser
from StringIO import StringIO
from unittest import main, TestCase
from uuid import uuid4

from mock import call, patch

from brim import conf


class TestConf(TestCase):

    def test_true_values(self):
        self.assertEqual(
            conf.TRUE_VALUES, [v.lower() for v in conf.TRUE_VALUES])

    def test_false_values(self):
        self.assertEqual(
            conf.FALSE_VALUES, [v.lower() for v in conf.FALSE_VALUES])

    def test_true_false_values_distinct(self):
        self.assertEqual(
            set(), set(conf.TRUE_VALUES).intersection(set(conf.FALSE_VALUES)))

    def test_direct_store(self):
        d = {
            's1': {'o1': '1.1', 'o2': '1.2'},
            's2': {'o1': '2.1', 'o2': '2.2'}}
        self.assertEqual(d, conf.Conf(d).store)

    def test_files(self):
        f = ['one.conf', 'two.conf']
        self.assertEqual(f, conf.Conf({}, f).files)

    def test_get(self):
        self.assertEqual(
            '1.1', conf.Conf({'s1': {'o1': '1.1'}}).get('s1', 'o1'))

    def test_get_multi_section1(self):
        self.assertEqual(
            'yes',
            conf.Conf({
                's1': {'o1': 'yes'},
                's2': {'o1': 'no'}}).get(['s1', 's2'], 'o1'))

    def test_get_multi_section2(self):
        self.assertEqual(
            'yes',
            conf.Conf({
                's1': {'o1': 'no'},
                's2': {'o1': 'yes'}}).get(['s2', 's1'], 'o1'))

    def test_get_default(self):
        self.assertEqual('d', conf.Conf({}).get('s1', 'o1', 'd'))

    def test_get_multi_section_default(self):
        self.assertEqual('d', conf.Conf({}).get(['s1', 's2'], 'o1', 'd'))

    def test_get_default_orig_is_none(self):
        self.assertEqual(
            'd', conf.Conf({'s1': {'o1': None}}).get('s1', 'o1', 'd'))

    def test_get_default_orig_is_empty(self):
        self.assertEqual(
            'd', conf.Conf({'s1': {'o1': ''}}).get('s1', 'o1', 'd'))

    def test_get_default_orig_is_something(self):
        self.assertEqual(
            's', conf.Conf({'s1': {'o1': 's'}}).get('s1', 'o1', 'd'))

    def test_get_bool(self):
        self.assertTrue(
            conf.Conf({'s1': {'o1': 'True'}}).get_bool('s1', 'o1', False))
        self.assertFalse(
            conf.Conf({'s1': {'o1': 'False'}}).get_bool('s1', 'o1', True))

    def test_get_bool_default(self):
        self.assertTrue(conf.Conf({}).get_bool('s1', 'o1', True))
        self.assertFalse(conf.Conf({}).get_bool('s1', 'o1', False))

    @patch.object(conf, 'exit')
    def test_get_bool_error(self, mock_exit):
        conf.Conf({'s1': {'o1': 'z'}}).get_bool('s1', 'o1', True)
        mock_exit.assert_called_once_with(
            "Configuration value [s1] o1 of 'z' cannot be converted to "
            "boolean.")

    @patch.object(conf, 'exit')
    def test_get_bool_error_multisection(self, mock_exit):
        conf.Conf({'s1': {'o1': 'z'}}).get_bool(['s1', 's2'], 'o1', True)
        mock_exit.assert_called_once_with(
            "Configuration value [s1|s2] o1 of 'z' cannot be converted to "
            "boolean.")

    def test_get_int(self):
        self.assertEqual(
            1, conf.Conf({'s1': {'o1': '1'}}).get_int('s1', 'o1', -2))
        self.assertEqual(
            -2, conf.Conf({'s1': {'o1': '-2'}}).get_int('s1', 'o1', 1))

    def test_get_int_default(self):
        self.assertEqual(1, conf.Conf({}).get_int('s1', 'o1', 1))

    @patch.object(conf, 'exit')
    def test_get_int_error(self, mock_exit):
        conf.Conf({'s1': {'o1': 'z'}}).get_int('s1', 'o1', 1)
        mock_exit.assert_called_once_with(
            "Configuration value [s1] o1 of 'z' cannot be converted to int.")

    def test_get_float(self):
        self.assertEqual(
            1.1, conf.Conf({'s1': {'o1': '1.1'}}).get_float('s1', 'o1', -2.3))
        self.assertEqual(
            -2.3, conf.Conf({'s1': {'o1': '-2.3'}}).get_float('s1', 'o1', 1.1))

    def test_get_float_default(self):
        self.assertEqual(1.1, conf.Conf({}).get_float('s1', 'o1', 1.1))

    @patch.object(conf, 'exit')
    def test_get_float_error(self, mock_exit):
        conf.Conf({'s1': {'o1': 'z'}}).get_float('s1', 'o1', 1.1)
        mock_exit.assert_called_once_with(
            "Configuration value [s1] o1 of 'z' cannot be converted to float.")

    @patch.object(conf, 'expanduser', lambda p: 'userdir' if '~' in p else p)
    def test_get_path(self):
        self.assertEqual(
            '/1/1',
            conf.Conf({'s1': {'o1': '/1/1'}}).get_path('s1', 'o1', '/2/3'))
        self.assertEqual(
            'userdir',
            conf.Conf({'s1': {'o1': '~/1/1'}}).get_path('s1', 'o1', '/2/3'))

    @patch.object(conf, 'expanduser', lambda p: 'userdir' if '~' in p else p)
    def test_get_path_default(self):
        self.assertEqual('/1/1', conf.Conf({}).get_path('s1', 'o1', '/1/1'))
        self.assertEqual('userdir', conf.Conf({}).get_path('s1', 'o1', '~1/1'))

    @patch.object(conf, 'exit')
    def test_get_path_error(self, mock_exit):
        conf.Conf({'s1': {'o1': 11}}).get_path('s1', 'o1', 11)
        mock_exit.assert_called_once_with(
            "Configuration value [s1] o1 of 11 cannot be converted to path.")

    def test_str(self):
        d = {'s1': {'o1': '1.1', 'o2': '1.2'},
             's2': {'o1': '2.1', 'o2': '2.2'}}
        self.assertEqual(
            "Conf based on 'unknown files': " + str(d), str(conf.Conf(d)))
        f = ['one.conf', 'two.conf']
        self.assertEqual(
            'Conf based on ' + str(f) + ': ' + str(d), str(conf.Conf(d, f)))

    def test_repr(self):
        d = {'s1': {'o1': '1.1', 'o2': '1.2'},
             's2': {'o1': '2.1', 'o2': '2.2'}}
        self.assertEqual(
            "Conf based on 'unknown files': " + str(d), repr(conf.Conf(d)))
        f = ['one.conf', 'two.conf']
        self.assertEqual(
            'Conf based on ' + str(f) + ': ' + str(d), repr(conf.Conf(d, f)))

    @patch.object(conf, 'expanduser')
    def test_read_conf_calls_expanduser(self, mock_expanduser):
        u1 = uuid4().hex
        u2 = uuid4().hex
        mock_expanduser.return_value = 'mock'
        conf.read_conf([u1, u2])
        mock_expanduser.assert_has_calls([call(u1), call(u2)])

    @patch.object(conf.SafeConfigParser, 'read')
    @patch.object(conf, 'exit')
    def test_read_conf_exits_on_read_exception(self, mock_exit, mock_read):
        mock_read.side_effect = Error()
        conf.read_conf('test.conf')
        self.assertEqual(len(mock_exit.call_args_list), 1)
        args, kwargs = mock_exit.call_args_list[0]
        self.assertEqual(len(args), 1)
        self.assertEqual(len(kwargs), 0)
        self.assertTrue(args[0] is mock_read.side_effect)

    @patch.object(conf.SafeConfigParser, 'read')
    def test_read_conf_raises_read_exception_if_asked(self, mock_read):
        mock_read.side_effect = Error()
        exc = None
        try:
            conf.read_conf('test.conf', exit_on_read_exception=False)
        except Exception as err:
            exc = err
        self.assertTrue(exc is mock_read.side_effect)

    def test_read_conf(self):

        def read(slf, files):
            SafeConfigParser.readfp(slf, StringIO('''
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

        with patch('ConfigParser.SafeConfigParser.read', read):
            c = conf.read_conf(
                ['test1.conf', 'test2.conf'], exit_on_read_exception=False)
            self.assertEqual(
                c.store, {
                    'section1': {
                        'default1': '1', 'option1': '1.1', 'option2': '1.2'},
                    'section2': {
                        'default1': '1', 'option1': '2.1', 'option2': '2.2'}})
            self.assertEqual(c.files, ['test1.conf', 'test2.conf'])

    def test_read_conf_stops_after_50(self):

        def read(slf, files):
            SafeConfigParser.readfp(slf, StringIO('''
[brim]
additional_confs = same_file
            '''))
            return files

        with patch('ConfigParser.SafeConfigParser.read', read):
            exc = None
            try:
                conf.read_conf('test.conf', exit_on_read_exception=False)
            except Error as err:
                exc = err
            self.assertTrue(str(exc).startswith(
                'Tried to read more than 50 conf files.\n'
                'Recursion with [brim] additional_confs?\n'
                'Files read so far: test.conf same_file same_file'))

    @patch.object(conf, 'exit')
    def test_read_conf_stops_after_50_with_exit(self, mock_exit):

        def read(slf, files):
            SafeConfigParser.readfp(slf, StringIO('''
[brim]
additional_confs = same_file
            '''))
            return files

        with patch('ConfigParser.SafeConfigParser.read', read):
            mock_exit.side_effect = Error()
            exc = None
            try:
                conf.read_conf('test.conf')
            except Error as err:
                exc = err
            self.assertTrue(exc is mock_exit.side_effect)
            self.assertEqual(len(mock_exit.call_args_list), 1)
            args, kwargs = mock_exit.call_args_list[0]
            self.assertEqual(len(args), 1)
            self.assertEqual(len(kwargs), 0)
            self.assertTrue(str(args[0]).startswith(
                'Tried to read more than 50 conf files.\n'
                'Recursion with [brim] additional_confs?\n'
                'Files read so far: test.conf same_file same_file'))


if __name__ == '__main__':
    main()
