"""Module for working with HTTP Form POSTs iteratively.

.. warning::

    This is an early version of this module. It has no tests, limited
    documentation, and is subject to major changes.

Provides tools for parsing an HTTP Form POST without reading the whole
thing into memory first. Many thanks to Michael Barton for the original
prototype which I mangled into OpenStack Swift's formpost middleware and
then into this module.

The basic usage is to iterate over iter_form results, which are
rfc822.Message instances::

    from brim.httpform import iter_form, parse_attrs

    def wsgi_app(env, start_response):
        for message in iter_form(env):
            body = message.fp.read()
            value, attrs = \\
                parse_attrs(message.getheader('content-disposition'))
            if value != 'form-data':
                continue
            if 'filename' in attrs:
                filevarname = attrs['name']
                filename = attrs['filename']
                filecontent = body
            else:
                varname = attrs['name']
                varvalue = body

See also the simple test at the end of the source file.
"""
"""Copyright and License.

Copyright 2012-2014 Gregory Holt
Copyright 2011 OpenStack, LLC.

Original source taken from OpenStack Swift FormPost middleware and
modified to be more generic.

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
import re
from rfc822 import Message


_ATTRIBUTES_RE = re.compile(r'(\w+)=(".*?"|[^";]+)(; ?|$)')


class FormInvalid(Exception):
    pass


def parse_attrs(header):
    """Returns (value, attr_dict) for an HTTP attr header.

    Given a header like::

        Content-Disposition: form-data; name="abc"; filename="test.html"

    Returns::

        ("form-data", {"name": "abc", "filename": "test.html"})

    Example usage with an rfc822.Message::

        value, attrs = parse_attrs(
            message.getheader('content-disposition'))
    """
    attributes = {}
    attrs = ''
    if '; ' in header:
        header, attrs = header.split('; ', 1)
    m = True
    while m:
        m = _ATTRIBUTES_RE.match(attrs)
        if m:
            attrs = attrs[len(m.group(0)):]
            attributes[m.group(1)] = m.group(2).strip('"')
    return header, attributes


class _FormPartFileLikeObject(object):

    def __init__(self, wsgi_input, boundary, input_buffer, read_chunk_size):
        self.no_more_data_for_this_message = False
        self.no_more_messages = False
        self.wsgi_input = wsgi_input
        self.boundary = boundary
        self.input_buffer = input_buffer
        self.read_chunk_size = read_chunk_size

    def read(self, length=None):
        if not length:
            length = self.read_chunk_size
        if self.no_more_data_for_this_message:
            return ''

        # read enough data to know whether we're going to run
        # into a boundary in next [length] bytes
        if len(self.input_buffer) < length + len(self.boundary) + 2:
            to_read = length + len(self.boundary) + 2
            while to_read > 0:
                chunk = self.wsgi_input.read(to_read)
                to_read -= len(chunk)
                self.input_buffer += chunk
                if not chunk:
                    self.no_more_messages = True
                    break

        boundary_pos = self.input_buffer.find(self.boundary)

        # boundary does not exist in the next (length) bytes
        if boundary_pos == -1 or boundary_pos > length:
            ret = self.input_buffer[:length]
            self.input_buffer = self.input_buffer[length:]
        # if it does, just return data up to the boundary
        else:
            ret, self.input_buffer = self.input_buffer.split(self.boundary, 1)
            self.no_more_messages = self.input_buffer.startswith('--')
            self.no_more_data_for_this_message = True
            self.input_buffer = self.input_buffer[2:]
        return ret

    def readline(self):
        if self.no_more_data_for_this_message:
            return ''
        boundary_pos = newline_pos = -1
        while newline_pos < 0 and boundary_pos < 0:
            chunk = self.wsgi_input.read(self.read_chunk_size)
            self.input_buffer += chunk
            newline_pos = self.input_buffer.find('\r\n')
            boundary_pos = self.input_buffer.find(self.boundary)
            if not chunk:
                self.no_more_messages = True
                break
        # found a newline
        if newline_pos >= 0 and \
                (boundary_pos < 0 or newline_pos < boundary_pos):
            # Use self.read to ensure any logic there happens...
            ret = ''
            to_read = newline_pos + 2
            while to_read > 0:
                chunk = self.read(to_read)
                # Should never happen since we're reading from input_buffer,
                # but just for completeness...
                if not chunk:
                    break
                to_read -= len(chunk)
                ret += chunk
            return ret
        else:  # no newlines, just return up to next boundary
            return self.read(len(self.input_buffer))


class CappedFileLikeObject(object):
    """Reads a limited amount from a file-like object.

    A file-like object wrapping another file-like object that raises an
    EOFError if the amount of data read exceeds a given max_file_size.

    This is useful to cap the form data size accepted::

        for message in iter_form(env):
            try:
                content = CappedFileLikeObject(message.fp, 4096).read()
            except EOFError:
                raise HTTPRequestEntityTooLarge(
                    'Max form part size is 4096.\\n')
    """

    def __init__(self, fp, max_file_size):
        self.fp = fp
        self.max_file_size = max_file_size
        self.amount_read = 0

    def read(self, size=None):
        ret = self.fp.read(size)
        self.amount_read += len(ret)
        if self.amount_read > self.max_file_size:
            raise EOFError('max_file_size exceeded')
        return ret

    def readline(self):
        ret = self.fp.readline()
        self.amount_read += len(ret)
        if self.amount_read > self.max_file_size:
            raise EOFError('max_file_size exceeded')
        return ret


def iter_form(env, read_chunk_size=4096):
    """Yields messages for an HTTP Form POST.

    Parses an HTTP Form POST and yields rfc822.Message instances for
    each form part. See the overview module :py:mod:`brim.httpform`
    for usage.

    :param env: The WSGI environment for the incoming request.
    :param read_chunk_size: The maximum amount to read at once from the
        incoming request.
    :returns: A generator yielding rfc822.Messages; be sure to fully
        read from the message.fp file-like object before continuing to
        the next message of the generator.
    """
    content_type, attrs = parse_attrs(env.get('CONTENT_TYPE') or '')
    if content_type != 'multipart/form-data':
        raise FormInvalid('Content-Type not "multipart/form-data".')
    boundary = attrs.get('boundary')
    if not boundary:
        raise FormInvalid('Content-Type does not define a form boundary.')
    boundary = '--' + boundary
    wsgi_input = env['wsgi.input']
    if wsgi_input.readline().strip() != boundary:
        raise FormInvalid('Invalid starting boundary.')
    boundary = '\r\n' + boundary
    input_buffer = ''
    done = False
    while not done:
        fp = _FormPartFileLikeObject(wsgi_input, boundary, input_buffer,
                                     read_chunk_size)
        yield Message(fp, 0)
        done = fp.no_more_messages
        input_buffer = fp.input_buffer


if __name__ == '__main__':
    # TODO: Real tests in brim.test.unit.test_httpform
    # This is just a quick test.
    from StringIO import StringIO

    wsgi_input = StringIO('\r\n'.join([
        '------WebKitFormBoundaryNcxTqxSlX7t4TDkR',
        'Content-Disposition: form-data; name="redirect"',
        '',
        'redirect value',
        '------WebKitFormBoundaryNcxTqxSlX7t4TDkR',
        'Content-Disposition: form-data; name="max_file_size"',
        '',
        str(15),
        '------WebKitFormBoundaryNcxTqxSlX7t4TDkR',
        'Content-Disposition: form-data; name="max_file_count"',
        '',
        str(25),
        '------WebKitFormBoundaryNcxTqxSlX7t4TDkR',
        'Content-Disposition: form-data; name="expires"',
        '',
        str(1234),
        '------WebKitFormBoundaryNcxTqxSlX7t4TDkR',
        'Content-Disposition: form-data; name="signature"',
        '',
        'sig value',
        '------WebKitFormBoundaryNcxTqxSlX7t4TDkR',
        'Content-Disposition: form-data; name="file1"; '
        'filename="testfile1.txt"',
        'Content-Type: text/plain',
        '',
        'Test File\nOne\n',
        '------WebKitFormBoundaryNcxTqxSlX7t4TDkR',
        'Content-Disposition: form-data; name="file2"; '
        'filename="testfile2.txt"',
        'Content-Type: text/plain',
        '',
        'Test\nFile\nTwo\n',
        '------WebKitFormBoundaryNcxTqxSlX7t4TDkR',
        'Content-Disposition: form-data; name="file3"; filename=""',
        'Content-Type: application/octet-stream',
        '',
        '',
        '------WebKitFormBoundaryNcxTqxSlX7t4TDkR--',
        '']))
    env = {
        'CONTENT_TYPE': 'multipart/form-data; '
        'boundary=----WebKitFormBoundaryNcxTqxSlX7t4TDkR',
        'wsgi.input': wsgi_input}
    for message in iter_form(env):
        print '---'
        body = message.fp.read()
        value, attrs = parse_attrs(message.getheader('content-disposition'))
        if value != 'form-data':
            continue
        if 'filename' in attrs:
            print 'FILE %s named %r:' % (attrs['name'], attrs['filename'])
            print body
        else:
            print 'VARIABLE %s = %r' % (attrs['name'], body)
