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
Contains utility classes for responding to WSGI requests. This isn't
WebOb http://www.webob.org/ but sometimes it's enough and you should
be able to upgrade easily to WebOb once you do need it.

Much like webob.exc there are classes for standard HTTP responses,
such as :py:class:`HTTPNotFound` for 404. Continuing with webob.exc
similarities, these classes are all subclasses of
:py:class:`HTTPException` and therefore can be raised and caught as
well as used as WSGI apps. The 2xx classes are all subclasses of
:py:class:`HTTPOk`, 3xx subclasses of :py:class:`HTTPRedirection`,
4xx subclasses of :py:class:`HTTPClientError`, and 5xx subclasses of
:py:class:`HTTPServerError`. :py:class:`HTTPClientError` and
:py:class:`HTTPServerError` also both subclass :py:class:`HTTPError`,
like webob.exc.

Instead of a Request object, this package just provides some simpler
classes and functions, like :py:class:`QueryParser` and
:py:func:`get_header_int`, and some replacement functions like
:py:func:`quote` (it's Unicode-safe by using UTF8).
"""

from urllib import quote as urllib_quote
from urlparse import parse_qs

from brim.conf import FALSE_VALUES, TRUE_VALUES


#: Translates an HTTP status code to an English status reason string,
#: such as CODE2NAME[201] = 'Created'.
CODE2NAME = {100: 'Continue',
             101: 'Switching Protocols',
             102: 'Processing',
             200: 'OK',
             201: 'Created',
             202: 'Accepted',
             203: 'Non-Authoritative Information',
             204: 'No Content',
             205: 'Reset Content',
             206: 'Partial Content',
             207: 'Multi-Status',
             208: 'Already Reported',
             226: 'IM Used',
             300: 'Multiple Choices',
             301: 'Moved Permanently',
             302: 'Found',
             303: 'See Other',
             304: 'Not Modified',
             305: 'Use Proxy',
             307: 'Temporary Redirect',
             400: 'Bad Request',
             401: 'Unauthorized',
             402: 'Payment Required',
             403: 'Forbidden',
             404: 'Not Found',
             405: 'Method Not Allowed',
             406: 'Not Acceptable',
             407: 'Proxy Authentication Required',
             408: 'Request Timeout',
             409: 'Conflict',
             410: 'Gone',
             411: 'Length Required',
             412: 'Precondition Failed',
             413: 'Request Entity Too Large',
             414: 'Request-URI Too Long',
             415: 'Unsupported Media Type',
             416: 'Requested Range Not Satisfiable',
             417: 'Expectation Failed',
             422: 'Unprocessable Entity',
             423: 'Locked',
             424: 'Failed Dependency',
             426: 'Upgrade Required',
             500: 'Internal Server Error',
             501: 'Not Implemented',
             502: 'Bad Gateway',
             503: 'Service Unavailable',
             504: 'Gateway Timeout',
             505: 'HTTP Version Not Supported',
             506: 'Variant Also Negotiates',
             507: 'Insufficient Storage',
             508: 'Loop Detected',
             510: 'Not Extended'}


class HTTPException(Exception):
    """
    Root class of all brim.http response classes.

    :param body: The body of the response. If the body has a length
                 (as determined by len(body)) and the headers don't
                 have a content-length or transfer-encoding, the
                 content-length will be set the body's length.
    :param headers: A dict of the headers to include in the response.
    :param code: The HTTP response code to give; defaults to 500.
    """

    def __init__(self, body=None, headers=None, code=500):
        Exception.__init__(self,
            '%s %s %s' % (code, CODE2NAME.get(code, 'Status'), body or '-'))
        self.code = code
        self.body = body or ''
        if not headers:
            headers = {}
        self.headers = {}
        for k, v in headers.iteritems():
            self.headers[k.lower()] = v
        if 'content-length' not in self.headers and \
                'transfer-encoding' not in self.headers and \
                hasattr(self.body, '__len__'):
            self.headers['content-length'] = len(self.body)
        if 'content-type' not in self.headers:
            self.headers['content-type'] = 'text/plain'

    def __call__(self, env, start_response):
        code = self.code
        if self.code == 200:
            try:
                if int(self.headers['content-length']) == 0:
                    code = 204
            except:
                pass
        start_response(
            '%s %s' % (code, CODE2NAME.get(code, 'Status')),
            [(k.title(), str(v)) for k, v in self.headers.iteritems()])
        if env['REQUEST_METHOD'] == 'HEAD':
            return []
        return [self.body]


HTTPResponse = HTTPException


class HTTPInformational(HTTPException):

    def __init__(self, body=None, headers=None, code=100):
        HTTPException.__init__(self, body, headers, code)


class HTTPContinue(HTTPInformational):

    def __init__(self, body=None, headers=None, code=100):
        HTTPInformational.__init__(self, body, headers, code)


class HTTPSwitchingProtocols(HTTPInformational):

    def __init__(self, body=None, headers=None, code=101):
        HTTPInformational.__init__(self, body, headers, code)


class HTTPProcessing(HTTPInformational):

    def __init__(self, body=None, headers=None, code=102):
        HTTPInformational.__init__(self, body, headers, code)


class HTTPSuccess(HTTPException):

    def __init__(self, body=None, headers=None, code=200):
        HTTPException.__init__(self, body, headers, code)


HTTPOk = HTTPOK = HTTPSuccess


class HTTPCreated(HTTPSuccess):

    def __init__(self, body=None, headers=None):
        HTTPSuccess.__init__(self, body, headers, 201)


class HTTPAccepted(HTTPSuccess):

    def __init__(self, body=None, headers=None):
        HTTPSuccess.__init__(self, body, headers, 202)


class HTTPNonAuthoritativeInformation(HTTPSuccess):

    def __init__(self, body=None, headers=None):
        HTTPSuccess.__init__(self, body, headers, 203)


class HTTPNoContent(HTTPSuccess):

    def __init__(self, body=None, headers=None):
        HTTPSuccess.__init__(self, body, headers, 204)


class HTTPResetContent(HTTPSuccess):

    def __init__(self, body=None, headers=None):
        HTTPSuccess.__init__(self, body, headers, 205)


class HTTPPartialContent(HTTPSuccess):

    def __init__(self, body=None, headers=None):
        HTTPSuccess.__init__(self, body, headers, 206)


class HTTPMultiStatus(HTTPSuccess):

    def __init__(self, body=None, headers=None):
        HTTPSuccess.__init__(self, body, headers, 207)


class HTTPAlreadyReported(HTTPSuccess):

    def __init__(self, body=None, headers=None):
        HTTPSuccess.__init__(self, body, headers, 208)


class HTTPIMUsed(HTTPSuccess):

    def __init__(self, body=None, headers=None):
        HTTPSuccess.__init__(self, body, headers, 226)


class HTTPRedirection(HTTPException):

    def __init__(self, body=None, headers=None, code=300):
        HTTPException.__init__(self, body, headers, code)


HTTPMultipleChoices = HTTPRedirection


class HTTPMovedPermanently(HTTPRedirection):

    def __init__(self, body=None, headers=None, code=301):
        HTTPRedirection.__init__(self, body, headers, code)


class HTTPFound(HTTPRedirection):

    def __init__(self, body=None, headers=None, code=302):
        HTTPRedirection.__init__(self, body, headers, code)


class HTTPSeeOther(HTTPRedirection):

    def __init__(self, body=None, headers=None, code=303):
        HTTPRedirection.__init__(self, body, headers, code)


class HTTPNotModified(HTTPRedirection):

    def __init__(self, body=None, headers=None, code=304):
        HTTPRedirection.__init__(self, body, headers, code)


class HTTPUseProxy(HTTPRedirection):

    def __init__(self, body=None, headers=None, code=305):
        HTTPRedirection.__init__(self, body, headers, code)


class HTTPTemporaryRedirect(HTTPRedirection):

    def __init__(self, body=None, headers=None, code=307):
        HTTPRedirection.__init__(self, body, headers, code)


class HTTPError(HTTPException):

    def __init__(self, body=None, headers=None, code=500):
        HTTPException.__init__(self, body, headers, code)


class HTTPClientError(HTTPError):

    def __init__(self, body=None, headers=None, code=400):
        HTTPError.__init__(self, body, headers, code)


HTTPBadRequest = HTTPClientError


class HTTPUnauthorized(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 401)


class HTTPPaymentRequired(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 402)


class HTTPForbidden(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 403)


class HTTPNotFound(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 404)


class HTTPMethodNotAllowed(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 405)


class HTTPNotAcceptable(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 406)


class HTTPProxyAuthenticationRequired(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 407)


class HTTPRequestTimeout(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 408)


class HTTPConflict(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 409)


class HTTPGone(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 410)


class HTTPLengthRequired(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 411)


class HTTPPreconditionFailed(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 412)


class HTTPRequestEntityTooLarge(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 413)


class HTTPRequestURITooLong(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 414)


class HTTPUnsupportedMediaType(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 415)


class HTTPRequestedRangeNotSatisfiable(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 416)


class HTTPExpectationFailed(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 417)


class HTTPUnprocessableEntity(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 422)


class HTTPLocked(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 423)


class HTTPFailedDependency(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 424)


class HTTPUpgradeRequired(HTTPClientError):

    def __init__(self, body=None, headers=None):
        HTTPClientError.__init__(self, body, headers, 426)


class HTTPServerError(HTTPError):

    def __init__(self, body=None, headers=None, code=500):
        HTTPError.__init__(self, body, headers, code)


HTTPInternalServerError = HTTPServerError


class HTTPNotImplemented(HTTPServerError):

    def __init__(self, body=None, headers=None):
        HTTPServerError.__init__(self, body, headers, 501)


class HTTPBadGateway(HTTPServerError):

    def __init__(self, body=None, headers=None):
        HTTPServerError.__init__(self, body, headers, 502)


class HTTPServiceUnavailable(HTTPServerError):

    def __init__(self, body=None, headers=None):
        HTTPServerError.__init__(self, body, headers, 503)


class HTTPGatewayTimeout(HTTPServerError):

    def __init__(self, body=None, headers=None):
        HTTPServerError.__init__(self, body, headers, 504)


class HTTPHTTPVersionNotSupported(HTTPServerError):

    def __init__(self, body=None, headers=None):
        HTTPServerError.__init__(self, body, headers, 505)


class HTTPVariantAlsoNegotiates(HTTPServerError):

    def __init__(self, body=None, headers=None):
        HTTPServerError.__init__(self, body, headers, 506)


class HTTPInsufficientStorage(HTTPServerError):

    def __init__(self, body=None, headers=None):
        HTTPServerError.__init__(self, body, headers, 507)


class HTTPLoopDetected(HTTPServerError):

    def __init__(self, body=None, headers=None):
        HTTPServerError.__init__(self, body, headers, 508)


class HTTPNotExtended(HTTPServerError):

    def __init__(self, body=None, headers=None):
        HTTPServerError.__init__(self, body, headers, 510)


class QueryParser(object):
    """
    Parses an HTTP query string and provides convenient retrieval
    methods for parameter values.

    :param query_string: The HTTP query string, such as in a WSGI
                         env['QUERY_STRING']. If using something
                         other than WSGI's QUERY_STRING, be sure you
                         do **not** include the question mark that
                         separates the path?query string or it will
                         be translated as the first character of the
                         first parameter.
    """

    def __init__(self, query_string=None):
        self.query = parse_qs(query_string or '', keep_blank_values=True)

    def get(self, name, default=None, last_only=True):
        """
        Returns the value of the query parameter, or the default
        value if the parameter does not exist.

        :param name: The name of the query parameter to retrieve.
        :param default: The default value if the parameter does not
                        exist.
        :param last_only: If True (the default), only the last value
                          of the parameter will be returned if the
                          parameter is specified multiple times. If
                          False, all values will be returned in a
                          list (even if there is only one value).
        """
        v = self.query.get(name)
        if v is None:
            return default
        if last_only:
            return v[-1]
        return v

    def get_boolean(self, name, default=None):
        """
        Returns the boolean value of the query parameter, or the
        default value if the parameter does not exist.

        If the parameter is included in the query string, but has no
        value (such as ?param), then ``not default`` will be
        returned.

        Otherwise, the parameter value will be checked against known
        TRUE_VALUES and FALSE_VALUES for translation, or
        HTTPBadRequest will be raised if the value cannot be
        translated.

        :param name: The name of the query parameter to retrieve.
        :param default: The default value if the parameter does not
                        exist.
        """
        v = self.get(name)
        if v is None:
            return default
        # Parameter included with no value, means invert the default.
        if not v:
            return not default
        if v.lower() in FALSE_VALUES:
            return False
        if v.lower() in TRUE_VALUES:
            return True
        raise HTTPBadRequest(
            'Query parameter %r value %r not boolean.\n' % (name, v))

    def get_int(self, name, default=None):
        """
        Returns the int value of the query parameter, or the default
        value if the parameter does not exist.

        :param name: The name of the query parameter to retrieve.
        :param default: The default value if the parameter does not
                        exist or has no value.
        """
        v = self.get(name)
        if v is None:
            return default
        try:
            return int(v)
        except ValueError, err:
            raise HTTPBadRequest(
                'Query parameter %r value %r not int.\n' % (name, v))

    def get_float(self, name, default=None):
        """
        Returns the float value of the query parameter, or the
        default value if the parameter does not exist.

        :param name: The name of the query parameter to retrieve.
        :param default: The default value if the parameter does not
                        exist or has no value.
        """
        v = self.get(name)
        if v is None:
            return default
        try:
            return float(v)
        except ValueError, err:
            raise HTTPBadRequest(
                'Query parameter %r value %r not float.\n' % (name, v))


def get_header_int(env, name, default=None):
    """
    Returns the int value of an HTTP header.

    :param env: Standard WSGI env to read from.
    :param name: The name of the header to retrieve.
    :param default: If specified, the default value will be used if
                    the header cannot be found. If not specified, the
                    header value will be considered required, and
                    HTTPBadRequest will be raised if the header is
                    missing.
    :returns: The int value of the header, or raises HTTPBadRequest
              if the header can't be translated to an integer or if
              the header is missing and required.
    """
    env_name = 'HTTP_' + name.upper().replace('-', '_')
    if env_name not in env:
        if default is not None:
            return default
        else:
            raise HTTPBadRequest(
                'Requires %s header.\n' % name.title())
    try:
        return int(env[env_name])
    except ValueError:
        raise HTTPBadRequest(
            'Invalid %s header %r.\n' % (name.title(), env[env_name]))


def quote(value, safe='/'):
    """
    Patched version of urllib.quote that encodes UTF8 strings before
    quoting.
    """
    if isinstance(value, unicode):
        value = value.encode('utf8')
    return urllib_quote(value, safe)
