"""Provides a simple way to work with configuration files.

This module can translate a ConfigParser-style configuration file into a
simple dict, wrapping that with a :py:class:`Conf` class providing
convenient "get" functions that work much like dict's "get" method
(return None or the default value provided if the section or option is
missing) for various value types.

Simple Example Using :py:func:`read_conf`::

    from sys import exit

    from brim.conf import read_conf

    conf = read_conf(['/etc/myco/myapp.conf', '~/.myapp.conf'])
    if not conf.files:
        exit('No configuration found.')
    port = conf.get_int('server', 'port', 1234)
    print 'Using port', port

By default, any error parsing the conf files or converting a value calls
sys.exit with an explanatory message. But you can override this behavior
by setting exit_on_read_exception to False and setting the
:py:meth:`Conf.error` method to your own method.

More Complex Example With Overrides::

    from ConfigParser import Error
    from sys import exit

    from brim.conf import read_conf

    try:
        conf = read_conf(
            ['/etc/myco/myapp.conf', '~/.myapp.conf'],
            exit_on_read_exception=False)
    except Error as err:
        exit('Config read error: ' + str(err))
    if not conf.files:
        exit('No configuration found.')

    def custom_error(section, option, value, conversion_type, err):
        if not isinstance(section, basestring):
            section = '|'.join(section)  # Handle iter of sections
        raise Exception(
            'Configuration value [%s] %s of %r cannot be converted '
            'to %s.' % (section, option, value, conversion_type))

    conf.error = custom_error
    try:
        port = conf.get_int('server', 'port', 1234)
    except Exception as err:
        exit('Config conversion error: ' + str(err))
    print 'Using port', port

Another feature of read_conf is that if a conf file has a [brim]
additional_confs setting, the files listed there are also be parsed.
This lets an end user make a conf file to be included by one or more
other conf files. Splitting configuration like this can make deployment
to clusters easier. For example::

    [brim]
    additional_confs = /etc/common.conf "/another file.conf" ~/.common.conf
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
from ConfigParser import Error, NoOptionError, NoSectionError, SafeConfigParser
from csv import reader
from os.path import expanduser
from sys import exit
from textwrap import wrap


TRUE_VALUES = ['1', 'on', 't', 'true', 'y', 'yes']
"""A list of lowercase string values that equate to True."""

FALSE_VALUES = ['0', 'f', 'false', 'n', 'no', 'off']
"""A list of lowercase string values that equate to False."""


class Conf(object):
    """Wraps a configuration dict for richer access methods.

    Within the dict store, each key is a section name and each value is
    another dict. Each section dict key is an option name and each value
    the actual value of the section/option within the conf. The list of
    file names the configuration was read from may optionally be stored.

    Normally Conf instances are created with the global function
    :py:func:`read_conf` but you can construct Conf instances directly
    as well::

        # Normally...
        conf = read_conf(['/etc/myco/myapp.conf', '~/.myapp.conf'])

        # Directly...
        conf = Conf({
            'section1': {'option1.1': 'a', 'option1.2': 'b'},
            'section2': {'option2.1': 'c', 'option2.2': 'd'}})

    :param store: A dict representing the configuration, as described
        above.
    :param files: A list of file names the configuration was read from.
    """

    def __init__(self, store, files=None):
        self.store = store
        """A dict containing the configuration information.

        Each dict key is a section name and each value is another dict.
        Each section dict key is an option name and each value the
        actual value of the section/option within the conf.
        """
        self.files = files
        """A list of source conf file names the conf was read from."""

    def get(self, section, option, default=None):
        """Returns the value of the section/option."""
        if isinstance(section, basestring):
            return (self.store.get(section) or {}).get(option) or default
        else:
            for section in section:
                value = self.store.get(section)
                if value:
                    value = value.get(option)
                    if value:
                        return value
            return default

    def get_bool(self, section, option, default):
        """Returns the boolean value of the section/option."""
        value = self.get(section, option, default)
        if value is True or value is False:
            return value
        if value.lower() in TRUE_VALUES:
            return True
        if value.lower() in FALSE_VALUES:
            return False
        self.error(section, option, value, 'boolean', None)

    def get_int(self, section, option, default):
        """Returns the int value of the section/option."""
        value = self.get(section, option, default)
        try:
            return int(value)
        except ValueError as err:
            self.error(section, option, value, 'int', err)

    def get_float(self, section, option, default):
        """Returns the float value of the section/option."""
        value = self.get(section, option, default)
        try:
            return float(value)
        except ValueError as err:
            self.error(section, option, value, 'float', err)

    def get_path(self, section, option, default=None):
        """Returns the path value of the section/option.

        This is different that just retrieving a string only in that it
        calls os.path.expanduser on the value, translating ~/path and
        ~user/path constructs.
        """
        value = self.get(section, option, default)
        if not value:
            return value
        try:
                return expanduser(value)
        except AttributeError as err:
            self.error(section, option, value, 'path', err)

    def error(self, section, option, value, conversion_type, err):
        """Handles an error converting a section/option value.

        This function is called when one of the "get" methods cannot
        convert a value. By default, this method calls sys.exit with an
        explanatory message, but you can override it by setting
        Conf.error to another method.

        An example of overriding to raise an Exception::

            def _error(section, option, value, conversion_type, err):
                raise Exception(
                    'Configuration value [%s] %s of %r cannot be '
                    'converted to %s.' %
                    (section, option, value, conversion_type))

            conf = read_conf(['some.conf'])
            conf.error = _error

        Note that the section parameter may have been given as an
        iterator of sections rather than just one section name.

        :param section: The section name (or an iterator of section
            names) within the conf that was read.
        :param option: The option name within the section that was read.
        :param value: The value read and failed conversion.
        :param conversion_type: The name of the type of conversion that
            failed, such as ``'boolean'``, ``'int'``, ``'float'``, or
            ``path``.
        :param err: The Exception that was raised, if any, during the
            conversion.
        """
        if not isinstance(section, basestring):
            section = '|'.join(section)  # Handle iter of sections
        exit(
            'Configuration value [%s] %s of %r cannot be converted to %s.' %
            (section, option, value, conversion_type))

    def __str__(self):
        return 'Conf based on %r: %r' % (
            self.files or 'unknown files', self.store)

    def __repr__(self):
        return str(self)


def _read_conf(parser, conf_files_read, conf_file, exit_on_read_exception):
    if len(conf_files_read) > 50:
        msg = (
            'Tried to read more than 50 conf files.\n'
            'Recursion with [brim] additional_confs?\n' +
            '\n'.join(wrap(
                'Files read so far: ' + ' '.join(conf_files_read), width=79)))
        if exit_on_read_exception:
            exit(msg)
        else:
            raise Error(msg)
    if exit_on_read_exception:
        try:
            conf_files_read.extend(parser.read([expanduser(conf_file)]))
        except Error as err:
            exit(err)
    else:
        conf_files_read.extend(parser.read([expanduser(conf_file)]))
    try:
        additional_confs = parser.get('brim', 'additional_confs')
    except (NoSectionError, NoOptionError):
        pass
    else:
        parser.remove_option('brim', 'additional_confs')
        for conf_file in list(
                reader([additional_confs], delimiter=' '))[0]:
            _read_conf(
                parser, conf_files_read, conf_file, exit_on_read_exception)


def read_conf(conf_files, exit_on_read_exception=True):
    """Returns a new :py:class:`Conf` instance.

    The new instance is based on the results from reading the conf_files
    into a ConfigParser.SafeConfigParser.

    Note that if the parser does not have access to read a given file it
    acts as if it did not exist.

    If a conf file has a [brim] additional_confs setting, the files
    listed there are also be parsed.

    You may wish to check the :py:attr:`Conf.files` list to determine
    which files, if any, were read to form the Conf instance.

    On a parser error, calls sys.exit with an explanatory message by
    default. If you set exit_on_read_exception to False, the
    ConfigParser.Error be raised instead.

    :param conf_files: An iterable of conf files or a string
        representing a single conf file to read and translate.
        Values in files further into the list override any values from
        prior files. File names may use the ~/filename or ~user/filename
        format and are expanded with os.path.expanduser.
    :param exit_on_read_exception: A boolean that indicates whether
        sys.exit should be called on error or if a ConfigParser.Error
        should be raised instead.
    :returns: A new :py:class:`Conf` instance representing the
        configuration read from the conf_files.
    """
    if isinstance(conf_files, basestring):
        conf_files = [conf_files]
    parser = SafeConfigParser()
    conf_files_read = []
    for conf_file in conf_files:
        _read_conf(parser, conf_files_read, conf_file, exit_on_read_exception)
    store = {}
    for section in parser.sections():
        store[section] = dict(parser.items(section))
    return Conf(store, files=conf_files_read)
