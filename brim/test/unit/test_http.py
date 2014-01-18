"""Tests for brim.http."""
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

from mock import MagicMock

from brim import http


class TestHTTP(TestCase):

    def test_overall(self):
        for code, name in http.CODE2NAME.iteritems():
            n = 'HTTP' + name.replace(' ', '').replace('-', '')
            c = getattr(http, n)
            i = c()
            self.assertEqual(
                i.code, code, 'Code for %s %s != %s' % (n, i.code, code))
            self.assertTrue(isinstance(i, http.HTTPException))
            if code // 100 == 1:
                self.assertTrue(isinstance(i, http.HTTPInformational))
            elif code // 100 == 2:
                self.assertTrue(isinstance(i, http.HTTPSuccess))
            elif code // 100 == 3:
                self.assertTrue(isinstance(i, http.HTTPRedirection), name)
            elif code // 100 == 4:
                self.assertTrue(isinstance(i, http.HTTPError))
                self.assertTrue(isinstance(i, http.HTTPClientError))
            elif code // 100 == 5:
                self.assertTrue(isinstance(i, http.HTTPError))
                self.assertTrue(isinstance(i, http.HTTPServerError))

    def test_defaults(self):
        h = http.HTTPException()
        self.assertEqual(h.headers, {
            'content-length': '26', 'content-type': 'text/plain'})
        self.assertEquals(h.body, '500 Internal Server Error\n')

    def test_keeps_raw_header_values(self):
        o = object()
        h = http.HTTPException(
            headers={'content-length': 128, 'content-type': o})
        self.assertEqual(h.headers, {'content-length': 128, 'content-type': o})

    def test_no_default_body_when_content_length_set(self):
        h = http.HTTPException(headers={'content-length': 128})
        self.assertEquals(h.body, None)

    def test_no_default_body_when_transfer_encoding_set(self):
        h = http.HTTPException(headers={'transfer-encoding': 'chunked'})
        self.assertEquals(h.body, None)

    def test_lowercases_header_names(self):
        h = http.HTTPException(headers={
            'Content-Length': '123',
            'cOnteNT-type': 'blah/blah',
            'another': 'HeaderValue'})
        self.assertEqual(h.headers, {
            'content-length': '123',
            'content-type': 'blah/blah',
            'another': 'HeaderValue'})

    def test_default_content_length_with_body(self):
        h = http.HTTPException('abc')
        self.assertEqual(h.headers['content-length'], '3')

    def test_default_content_type_with_body(self):
        h = http.HTTPException('abc')
        self.assertEqual(h.headers['content-type'], 'text/plain')

    def test_call_default(self):
        mock_start_response = MagicMock()
        env = {'REQUEST_METHOD': 'GET'}
        body = http.HTTPException()(env, mock_start_response)
        mock_start_response.assert_called_once_with(
            '500 Internal Server Error',
            [('Content-Length', '26'), ('Content-Type', 'text/plain')])
        self.assertEqual(''.join(body), '500 Internal Server Error\n')

    def test_call_200(self):
        mock_start_response = MagicMock()
        env = {'REQUEST_METHOD': 'GET'}
        body = http.HTTPException(
            body='testvalue', code=200)(env, mock_start_response)
        mock_start_response.assert_called_once_with(
            '200 OK',
            [('Content-Length', '9'), ('Content-Type', 'text/plain')])
        self.assertEqual(''.join(body), 'testvalue')

    def test_call_200_to_204(self):
        mock_start_response = MagicMock()
        env = {'REQUEST_METHOD': 'GET'}
        body = http.HTTPException(
            body='', code=200)(env, mock_start_response)
        mock_start_response.assert_called_once_with(
            '204 No Content',
            [('Content-Length', '0'), ('Content-Type', 'text/plain')])
        self.assertEqual(''.join(body), '')

    def test_call_200_to_204_unless_screwy_content_length(self):
        mock_start_response = MagicMock()
        env = {'REQUEST_METHOD': 'GET'}
        body = http.HTTPException(
            body='', headers={'content-length': 'abc'},
            code=200)(env, mock_start_response)
        mock_start_response.assert_called_once_with(
            '200 OK',
            [('Content-Length', 'abc'), ('Content-Type', 'text/plain')])
        self.assertEqual(''.join(body), '')

    def test_call_head_keeps_content_length(self):
        mock_start_response = MagicMock()
        env = {'REQUEST_METHOD': 'HEAD'}
        body = http.HTTPException(
            body='testvalue', code=200)(env, mock_start_response)
        mock_start_response.assert_called_once_with(
            '200 OK',
            [('Content-Length', '9'), ('Content-Type', 'text/plain')])
        self.assertEqual(''.join(body), '')

    def test_call_converts_all_header_values_to_str(self):
        mock_start_response = MagicMock()
        env = {'REQUEST_METHOD': 'GET'}
        http.HTTPException(
            headers={
                'header1': 1,
                'header2': Exception('gets converted to a str'),
                'header3': u'gets utf8 encoded to a str \u00B6'
            })(env, mock_start_response)
        self.assertEqual(mock_start_response.call_count, 1)
        self.assertEqual(len(mock_start_response.call_args[0]), 2)
        h = dict(mock_start_response.call_args[0][1])
        self.assertEqual(h.get('Header1'), '1')
        self.assertEqual(h.get('Header2'), 'gets converted to a str')
        self.assertEqual(
            h.get('Header3'), 'gets utf8 encoded to a str \xc2\xb6')


class TestQueryParser(TestCase):

    def setUp(self):
        self.q = http.QueryParser(
            'empty1&empty2=&tp1=val1&tp2=val2a&tp2=val2b')

    def test_init_empty_works(self):
        q = http.QueryParser()
        q.get('nothing', '')

    def test_get(self):
        self.assertRaises(http.HTTPBadRequest, self.q.get, 'invalid')
        self.assertEqual(self.q.get('invalid', 1), 1)
        self.assertEqual(self.q.get('invalid', 1, False), 1)
        self.assertEqual(self.q.get('empty1'), '')
        self.assertEqual(self.q.get('empty1', 1), '')
        self.assertEqual(self.q.get('empty1', 1, False), [''])
        self.assertEqual(self.q.get('empty2'), '')
        self.assertEqual(self.q.get('empty2', 1), '')
        self.assertEqual(self.q.get('empty2', 1, False), [''])
        self.assertEqual(self.q.get('tp1'), 'val1')
        self.assertEqual(self.q.get('tp1', 1), 'val1')
        self.assertEqual(self.q.get('tp1', 1, False), ['val1'])
        self.assertEqual(self.q.get('tp2'), 'val2b')
        self.assertEqual(self.q.get('tp2', 1), 'val2b')
        self.assertEqual(self.q.get('tp2', 1, False), ['val2a', 'val2b'])

    def test_get_bool(self):
        self.assertRaises(http.HTTPBadRequest, self.q.get_bool, 'invalid')
        self.assertEqual(self.q.get_bool('invalid', True), True)
        self.assertEqual(self.q.get_bool('empty1'), True)
        self.assertEqual(self.q.get_bool('empty1', True), False)
        self.assertEqual(self.q.get_bool('empty2'), True)
        self.assertEqual(self.q.get_bool('empty2', True), False)
        self.assertRaises(http.HTTPBadRequest, self.q.get_bool, 'tp1')
        self.assertRaises(http.HTTPBadRequest, self.q.get_bool, 'tp1', True)
        self.assertRaises(http.HTTPBadRequest, self.q.get_bool, 'tp2')
        self.assertRaises(http.HTTPBadRequest, self.q.get_bool, 'tp2', True)
        for v in http.TRUE_VALUES:
            q = http.QueryParser('test=' + v)
            self.assertEqual(q.get_bool('test'), True, v)
            q = http.QueryParser('test=' + v.upper())
            self.assertEqual(q.get_bool('test'), True, v)
        for v in http.FALSE_VALUES:
            q = http.QueryParser('test=' + v)
            self.assertEqual(q.get_bool('test'), False, v)
            q = http.QueryParser('test=' + v.upper())
            self.assertEqual(q.get_bool('test'), False, v)

    def test_get_int(self):
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'invalid')
        self.assertEqual(self.q.get_int('invalid', 1234), 1234)
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'empty1')
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'empty1', 1234)
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'empty2')
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'empty2', 1234)
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'tp1')
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'tp1', 1234)
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'tp2')
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'tp2', 1234)
        q = http.QueryParser('test=123')
        self.assertEqual(q.get_int('test'), 123)
        q = http.QueryParser('test=-123')
        self.assertEqual(q.get_int('test'), -123)

    def test_get_float(self):
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'invalid')
        self.assertEqual(self.q.get_float('invalid', 1.2), 1.2)
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'empty1')
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'empty1', 1.2)
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'empty2')
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'empty2', 1.2)
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'tp1')
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'tp1', 1.2)
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'tp2')
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'tp2', 1.2)
        q = http.QueryParser('test=1.23')
        self.assertEqual(q.get_float('test'), 1.23)
        q = http.QueryParser('test=-1.23')
        self.assertEqual(q.get_float('test'), -1.23)

    def test_leading_question_mark_is_part_of_parameter_name(self):
        q = http.QueryParser('?one=two')
        self.assertEqual(q.get('one', 'notset'), 'notset')
        self.assertEqual(q.get('?one'), 'two')


class TestGlobals(TestCase):

    def test_get_header_bool(self):
        self.assertRaises(
            http.HTTPBadRequest, http.get_header_bool, {}, 'required')
        self.assertEqual(http.get_header_bool({}, 'missing', True), True)
        self.assertRaises(
            http.HTTPBadRequest, http.get_header_bool,
            {'HTTP_HEADER': 'invalid'}, 'header')
        self.assertRaises(
            http.HTTPBadRequest, http.get_header_bool,
            {'HTTP_HEADER': 'invalid'}, 'header', True)
        for v in http.TRUE_VALUES:
            self.assertEqual(
                http.get_header_bool({'HTTP_HEADER': v}, 'header'), True)
            self.assertEqual(http.get_header_bool(
                {'HTTP_HEADER': v.upper()}, 'header'), True)
        for v in http.FALSE_VALUES:
            self.assertEqual(
                http.get_header_bool({'HTTP_HEADER': v}, 'header'), False)
            self.assertEqual(http.get_header_bool(
                {'HTTP_HEADER': v.upper()}, 'header'), False)

    def test_get_header_int(self):
        self.assertEqual(http.get_header_int({}, 'header', 123), 123)
        self.assertEqual(
            http.get_header_int({'HTTP_HEADER': '123'}, 'header'), 123)
        self.assertRaises(
            http.HTTPBadRequest, http.get_header_int, {}, 'header')
        self.assertRaises(
            http.HTTPBadRequest, http.get_header_int,
            {'HTTP_HEADER': 'abc'}, 'header')

    def test_get_header_float(self):
        self.assertEqual(http.get_header_float({}, 'header', 1.3), 1.3)
        self.assertEqual(
            http.get_header_float({'HTTP_HEADER': '1.3'}, 'header'), 1.3)
        self.assertRaises(
            http.HTTPBadRequest, http.get_header_float, {}, 'header')
        self.assertRaises(
            http.HTTPBadRequest, http.get_header_float,
            {'HTTP_HEADER': 'abc'}, 'header')

    def test_quote(self):
        self.assertEqual(http.quote('abc'), 'abc')
        self.assertEqual(http.quote('a bc'), 'a%20bc')
        self.assertEqual(http.quote('a/bc'), 'a/bc')
        self.assertEqual(http.quote(u'a\u00B6bc'), 'a%C2%B6bc')


if __name__ == '__main__':
    main()
