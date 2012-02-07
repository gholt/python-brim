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
Provides a simpler way to work with configuration files by
translating a ConfigParser-style configuration file into a simpler
dict and then wrapping that with a Conf class providing convenient
"get" functions that work much like dict's "get" method (returns None
or the default value provided if the section or option is missing).


Simple Example::

    import sys

    from brim.conf import read_conf

    conf = read_conf(['/etc/myco/myapp.conf', '~/.myapp.conf'])
    if not conf.files:
        sys.exit('No configuration found.')
    port = conf.get_int('server', 'port', 1234)
    print 'Using port', port

By default, any errors parsing the conf files or converting values
will call sys.exit with an explanatory message. But you can override
these behaviors by setting exit_on_read_exception to False and
setting the Conf.error method to your own method.

More Complex Example With Overrides::

    import ConfigParser
    import sys

    from brim.conf import read_conf

    try:
        conf = read_conf(['/etc/myco/myapp.conf', '~/.myapp.conf'],
                         exit_on_read_exception=False)
    except ConfigParser.Error, err:
        sys.exit('Config read error: ' + str(err))
    if not conf.files:
        exit('No configuration found.')

    def custom_error(section, option, value, conversion_type, err):
        raise Exception('Configuration value [%s] %s of %r cannot be '
                        'converted to %s.' %
                        (section, option, value, conversion_type))

    conf.error = custom_error
    try:
        port = conf.get_int('wsgi_server', 'port', 1234)
    except Exception, err:
        sys.exit('Config conversion error: ' + str(err))
    print 'Using port', port

Another feature of read_conf is that if a conf file has a [brim]
additional_confs setting, the files listed there will also be parsed.
This lets an end user make a conf file to be included by one or more
other conf files. Splitting configuration like this can make
deployment to clusters easier. For example::

    [brim]
    additional_confs = /etc/common.conf "/another file.conf" ~/.common.conf
"""

__all__ = ['Conf', 'read_conf', 'TRUE_VALUES', 'FALSE_VALUES']

from ConfigParser import SafeConfigParser, Error
from csv import reader as csv_reader
from os.path import expanduser
from sys import exit
from textwrap import wrap


#: The list of str values that equate to True, all lowercase.
TRUE_VALUES = ['1', 'on', 't', 'true', 'y', 'yes']

#: The list of str values that equate to False, all lowercase.
FALSE_VALUES = ['0', 'f', 'false', 'n', 'no', 'off']


class Conf(object):
    """
    Wraps a dict of conf sections, each value a dict of conf options,
    each value the actual value of the section/option within the
    conf. The list of file names the configuration was read from may
    optionally be stored.

    The usual way to use Conf after instantiation is just through the
    "get" methods, but direct access to the store dict and the files
    list is also supported.

    Normally Conf instances are created with the global func
    :py:func:`read_conf` but you can construct Conf instances
    directly as well::

        # Normally...
        conf = read_conf(['/etc/myco/myapp.conf', '~/.myapp.conf'])

        # Directly...
        conf = Conf({
            'section1': {'option1.1': 'a', 'option1.2': 'b'},
            'section2': {'option2.1': 'c', 'option2.2': 'd'}})

    :param store: A dict representing the configuration, as described
                  above.
    :param files: Optional list of file names the configuration was
                  read from.
    """

    def __init__(self, store, files=None):
        #: A dict of conf sections, each value a dict of conf
        #: options, each value the actual value of the section/option
        #: within the conf.
        self.store = store
        #: A list of source conf file names the conf was read from.
        self.files = files

    def get(self, section, option, default=None):
        """
        Returns the value of the section/option in the conf store or
        the default value given (or None) if the section/option does
        not exist.

        :param section: The section name within the conf to read.
        :param option: The option name within the section to read.
        :param default: The default value to return if the section or
                        option does not exist or is set to None.
        """
        return (self.store.get(section) or {}).get(option) or default

    def get_boolean(self, section, option, default):
        """
        Returns the boolean value of the section/option in the conf
        store or the default value given if the section/option does
        not exist.

        This will call :py:func:`error` if the value cannot be
        converted to a boolean.

        :param section: The section name within the conf to read.
        :param option: The option name within the section to read.
        :param default: The default value to return if the section or
                        option does not exist or is set to None.
        """
        value = self.get(section, option, default)
        if value is True or value is False:
            return value
        if value.lower() in TRUE_VALUES:
            return True
        if value.lower() in FALSE_VALUES:
            return False
        self.error(section, option, value, 'boolean', None)

    def get_int(self, section, option, default):
        """
        Returns the int value of the section/option in the conf store
        or the default value given if the section/option does not
        exist.

        This will call :py:func:`error` if the value cannot be
        converted to an int.

        :param section: The section name within the conf to read.
        :param option: The option name within the section to read.
        :param default: The default value to return if the section or
                        option does not exist or is set to None.
        """
        value = self.get(section, option, default)
        try:
            return int(value)
        except ValueError, err:
            self.error(section, option, value, 'int', err)

    def get_float(self, section, option, default):
        """
        Returns the float value of the section/option in the conf
        store or the default value given if the section/option does
        not exist.

        This will call :py:func:`error` if the value cannot be
        converted to a float.

        :param section: The section name within the conf to read.
        :param option: The option name within the section to read.
        :param default: The default value to return if the section or
                        option does not exist or is set to None.
        """
        value = self.get(section, option, default)
        try:
            return float(value)
        except ValueError, err:
            self.error(section, option, value, 'float', err)

    def error(self, section, option, value, conversion_type, err):
        """
        This function is called when one of the "get" methods cannot
        convert a value. By default, this method will call sys.exit
        with an explanatory message, but you can override it by
        setting Conf.error to another method.

        An example of overriding to raise an Exception::

            def _error(section, option, value, conversion_type, err):
                raise Exception('Configuration value [%s] %s of %r '
                                'cannot be converted to %s.' %
                                (section, option, value,
                                 conversion_type))

            conf = read_conf(['some.conf'])
            conf.error = _error

        :param section: The section name within the conf that was
                        read.
        :param option: The option name within the section that was
                       read.
        :param value: The str value read and failed conversion.
        :param conversion_type: The name of the type of conversion
                                that failed, such as ``'boolean'``,
                                ``'int'``, or ``'float'``.
        :param err: The Exception that was raised, if any, during the
                    conversion.
        """
        exit('Configuration value [%s] %s of %r cannot be converted to %s.' %
             (section, option, value, conversion_type))

    def __str__(self):
        return 'Conf based on %r: %r' % \
               (self.files or 'unknown files', self.store)

    def __repr__(self):
        return str(self)


def _read_conf(parser, conf_files_read, conf_file, exit_on_read_exception):
    if len(conf_files_read) > 50:
        msg = 'Tried to read more than 50 conf files.\n' \
              'Recursion with [brim_conf] additional_confs?\n' + \
              '\n'.join(wrap('Files read so far: ' + ' '.join(conf_files_read),
                             width=79))
        if exit_on_read_exception:
            exit(msg)
        else:
            raise Exception(msg)
    if exit_on_read_exception:
        try:
            conf_files_read.extend(parser.read([expanduser(conf_file)]))
        except Error, err:
            exit(err)
    else:
        conf_files_read.extend(parser.read([expanduser(conf_file)]))
    try:
        additional_confs = parser.get('brim', 'additional_confs')
        parser.remove_option('brim', 'additional_confs')
        for conf_file in list(csv_reader([additional_confs],
                              delimiter=' '))[0]:
            _read_conf(parser, conf_files_read, conf_file,
                       exit_on_read_exception)
    except Error:
        pass


def read_conf(conf_files, exit_on_read_exception=True):
    """
    Returns a new Conf instance based on the results from reading the
    conf_files into a ConfigParser.SafeConfigParser.

    Note that if the parser does not have access to read a given file
    it will act as if it did not exist.

    If a conf file has a [brim] additional_confs setting, the
    files listed there will also be parsed.

    You may wish to check the Conf.files list to determine which
    files, if any, were read to form the Conf instance.

    On a parser error, this will call sys.exit with an explanatory
    message by default. If you set exit_on_read_exception to False,
    the ConfigParser.Error will be raised instead.

    :param conf_files: A list of conf files to read and translate, in
                       order. Therefore, values in files further into
                       the list will override any values from prior
                       files. File names may use the ~/filename or
                       ~user/filename format and will be expanded
                       with os.path.expanduser.
    """
    parser = SafeConfigParser()
    conf_files_read = []
    for conf_file in conf_files:
        _read_conf(parser, conf_files_read, conf_file, exit_on_read_exception)
    store = {}
    for section in parser.sections():
        store[section] = dict(parser.items(section))
    return Conf(store, files=conf_files_read)
