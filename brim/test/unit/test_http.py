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

from unittest import main, TestCase

from brim import http


class TestHTTP(TestCase):

    def test_overall(self):
        for code, name in http.CODE2NAME.iteritems():
            n = 'HTTP' + name.replace(' ', '').replace('-', '')
            c = getattr(http, n)
            i = c()
            self.assertEquals(i.code, code,
                              'Code for %s %s != %s' % (n, i.code, code))
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

    def test_headers(self):
        h = http.HTTPException().headers
        self.assertEquals(h, {'content-length': 0,
                              'content-type': 'text/plain'})
        h = http.HTTPException(headers={'Content-Length': 128,
                                        'cOnteNT-type': 'blah/blah',
                                        'another': 'HeaderValue'}).headers
        self.assertEquals(h, {'content-length': 128,
                              'content-type': 'blah/blah',
                              'another': 'HeaderValue'})
        h = http.HTTPException(
            headers={'transfer-encoding': 'chunked'}).headers
        self.assertEquals(h, {'transfer-encoding': 'chunked',
                              'content-type': 'text/plain'})

    def test_call_default(self):
        start_response_calls = []

        def _start_response(*args):
            start_response_calls.append(args)

        env = {'REQUEST_METHOD': 'GET'}
        body = http.HTTPException()(env, _start_response)
        self.assertEquals(
            start_response_calls,
            [('500 Internal Server Error',
                [('Content-Length', '0'), ('Content-Type', 'text/plain')])])
        self.assertEquals(''.join(body), '')

    def test_call_200(self):
        start_response_calls = []

        def _start_response(*args):
            start_response_calls.append(args)

        env = {'REQUEST_METHOD': 'GET'}
        body = http.HTTPException(body='testvalue',
                                  code=200)(env, _start_response)
        self.assertEquals(
            start_response_calls,
            [('200 OK', [('Content-Length', '9'),
             ('Content-Type', 'text/plain')])])
        self.assertEquals(''.join(body), 'testvalue')

    def test_call_200_to_204(self):
        start_response_calls = []

        def _start_response(*args):
            start_response_calls.append(args)

        env = {'REQUEST_METHOD': 'GET'}
        body = http.HTTPException(body='',
                                  code=200)(env, _start_response)
        self.assertEquals(
            start_response_calls,
            [('204 No Content', [('Content-Length', '0'),
             ('Content-Type', 'text/plain')])])
        self.assertEquals(''.join(body), '')

    def test_call_200_to_204_unless_screwy_content_length(self):
        start_response_calls = []

        def _start_response(*args):
            start_response_calls.append(args)

        env = {'REQUEST_METHOD': 'GET'}
        body = http.HTTPException(body='', headers={'content-length': 'abc'},
                                  code=200)(env, _start_response)
        self.assertEquals(
            start_response_calls,
            [('200 OK', [('Content-Length', 'abc'),
             ('Content-Type', 'text/plain')])])
        self.assertEquals(''.join(body), '')

    def test_call_head_keeps_content_length(self):
        start_response_calls = []

        def _start_response(*args):
            start_response_calls.append(args)

        env = {'REQUEST_METHOD': 'HEAD'}
        body = http.HTTPException(body='testvalue',
                                  code=200)(env, _start_response)
        self.assertEquals(
            start_response_calls,
            [('200 OK', [('Content-Length', '9'),
             ('Content-Type', 'text/plain')])])
        self.assertEquals(''.join(body), '')


class TestQueryParser(TestCase):

    def setUp(self):
        self.q = http.QueryParser(
            'empty1&empty2=&tp1=val1&tp2=val2a&tp2=val2b')

    def test_init_empty_works(self):
        q = http.QueryParser()
        q.get('nothing', '')

    def test_get(self):
        self.assertRaises(http.HTTPBadRequest, self.q.get, 'invalid')
        self.assertEquals(self.q.get('invalid', 1), 1)
        self.assertEquals(self.q.get('invalid', 1, False), 1)
        self.assertEquals(self.q.get('empty1'), '')
        self.assertEquals(self.q.get('empty1', 1), '')
        self.assertEquals(self.q.get('empty1', 1, False), [''])
        self.assertEquals(self.q.get('empty2'), '')
        self.assertEquals(self.q.get('empty2', 1), '')
        self.assertEquals(self.q.get('empty2', 1, False), [''])
        self.assertEquals(self.q.get('tp1'), 'val1')
        self.assertEquals(self.q.get('tp1', 1), 'val1')
        self.assertEquals(self.q.get('tp1', 1, False), ['val1'])
        self.assertEquals(self.q.get('tp2'), 'val2b')
        self.assertEquals(self.q.get('tp2', 1), 'val2b')
        self.assertEquals(self.q.get('tp2', 1, False), ['val2a', 'val2b'])

    def test_get_bool(self):
        self.assertRaises(http.HTTPBadRequest, self.q.get_bool, 'invalid')
        self.assertEquals(self.q.get_bool('invalid', True), True)
        self.assertEquals(self.q.get_bool('empty1'), True)
        self.assertEquals(self.q.get_bool('empty1', True), False)
        self.assertEquals(self.q.get_bool('empty2'), True)
        self.assertEquals(self.q.get_bool('empty2', True), False)
        self.assertRaises(http.HTTPBadRequest, self.q.get_bool, 'tp1')
        self.assertRaises(http.HTTPBadRequest, self.q.get_bool, 'tp1', True)
        self.assertRaises(http.HTTPBadRequest, self.q.get_bool, 'tp2')
        self.assertRaises(http.HTTPBadRequest, self.q.get_bool, 'tp2', True)
        for v in http.TRUE_VALUES:
            q = http.QueryParser('test=' + v)
            self.assertEquals(q.get_bool('test'), True, v)
            q = http.QueryParser('test=' + v.upper())
            self.assertEquals(q.get_bool('test'), True, v)
        for v in http.FALSE_VALUES:
            q = http.QueryParser('test=' + v)
            self.assertEquals(q.get_bool('test'), False, v)
            q = http.QueryParser('test=' + v.upper())
            self.assertEquals(q.get_bool('test'), False, v)

    def test_get_int(self):
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'invalid')
        self.assertEquals(self.q.get_int('invalid', 1234), 1234)
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'empty1')
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'empty1', 1234)
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'empty2')
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'empty2', 1234)
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'tp1')
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'tp1', 1234)
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'tp2')
        self.assertRaises(http.HTTPBadRequest, self.q.get_int, 'tp2', 1234)
        q = http.QueryParser('test=123')
        self.assertEquals(q.get_int('test'), 123)
        q = http.QueryParser('test=-123')
        self.assertEquals(q.get_int('test'), -123)

    def test_get_float(self):
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'invalid')
        self.assertEquals(self.q.get_float('invalid', 1.2), 1.2)
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'empty1')
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'empty1', 1.2)
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'empty2')
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'empty2', 1.2)
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'tp1')
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'tp1', 1.2)
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'tp2')
        self.assertRaises(http.HTTPBadRequest, self.q.get_float, 'tp2', 1.2)
        q = http.QueryParser('test=1.23')
        self.assertEquals(q.get_float('test'), 1.23)
        q = http.QueryParser('test=-1.23')
        self.assertEquals(q.get_float('test'), -1.23)

    def test_leading_question_mark_is_part_of_parameter_name(self):
        q = http.QueryParser('?one=two')
        self.assertEquals(q.get('one', 'notset'), 'notset')
        self.assertEquals(q.get('?one'), 'two')


class TestGetHeaderInt(TestCase):

    def test_get_header_int(self):
        self.assertEquals(http.get_header_int({}, 'test-header', 123), 123)
        self.assertEquals(http.get_header_int(
            {'HTTP_TEST_HEADER': '123'}, 'test-header'), 123)
        self.assertRaises(http.HTTPBadRequest,
                          http.get_header_int, {}, 'test-header')
        self.assertRaises(http.HTTPBadRequest, http.get_header_int,
                          {'HTTP_TEST_HEADER': 'abc'}, 'test-header')


class TestQuote(TestCase):

    def test_quote(self):
        self.assertEquals(http.quote('abc'), 'abc')
        self.assertEquals(http.quote('a bc'), 'a%20bc')
        self.assertEquals(http.quote('a/bc'), 'a/bc')
        self.assertEquals(http.quote(u'a\u00B6bc'), 'a%C2%B6bc')


if __name__ == '__main__':
    main()
