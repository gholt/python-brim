"""Miscellaneous classes and functions."""
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

from collections import MutableMapping
from contextlib import contextmanager
from errno import EAGAIN, EEXIST, ENOENT
from fcntl import flock, LOCK_EX, LOCK_NB
from os import close as os_close, makedirs, open as os_open, O_RDONLY, \
    unlink as os_unlink
from os.path import exists
from time import sleep, time


class LockPathTimeout(Exception):
    """Raised by :py:func:`lock_path` if its timeout is reached."""
    pass


@contextmanager
def lock_path(path, timeout):
    """A context manager that attempts to gain an advisory lock.

    The advisory lock is attempted for the path given within the timeout
    given. Raises :py:class:`LockPathTimeout` if time expires before
    gaining the lock. If the lock is obtained, True is yielded and the
    lock relinquished when the context ends.

    For example::

        with lock_path(path, timeout):
            # do things inside path knowing others using the same
            # advisory locking mechanism will be blocked until you're
            # done.

    :param path: The path to gain an advisory lock on.
    :param timeout: The number of seconds to wait to gain the lock
        before raising :py:class:`LockPathTimeout`.
    """
    fd = os_open(path, O_RDONLY)
    try:
        try_until = time() + timeout
        while True:
            try:
                flock(fd, LOCK_EX | LOCK_NB)
                break
            except IOError as err:
                if err.errno != EAGAIN:
                    raise
            sleep(0.01)
            if time() >= try_until:
                raise LockPathTimeout(
                    'Timeout %ds trying to lock %r.' % (timeout, path))
        yield True
    finally:
        os_close(fd)


def make_dirs(path, mode=0o777):
    """os.makedirs but ignoring errors due to the path already existing.

    :param path: The path to create a directory and all parent
        directories for.
    :param mode: The permissions mode (masked with the current umask) to
        create new directories with; defaults to 0o777.
    """
    if not exists(path):
        try:
            makedirs(path, mode)
        except OSError as err:
            if err.errno != EEXIST:
                raise


def unlink(path):
    """os.unlink but ignoring errors due to the path already not existing."""
    try:
        os_unlink(path)
    except OSError as err:
        if err.errno != ENOENT:
            raise


class CaseInsensitiveDict(MutableMapping):
    """Simple case-insensitive dict.

    Why isn't this in Python standard lib? Or is it and hiding from me?

    Expects only strings as keys, or at least something that behaves
    like a string and has a lower() method.

    Retains the case of each key as most recently set.
    """

    def __init__(self, iterable=None, **kwargs):
        self._dict = {}
        if iterable is not None:
            self.update(iterable)
        if kwargs:
            self.update(**kwargs)

    def copy(self):
        return CaseInsensitiveDict(self._dict.itervalues())

    def __repr__(self):
        return repr(dict(self._dict.itervalues()))

    def __setitem__(self, key, value):
        self._dict[key.lower()] = (key, value)

    def __getitem__(self, key):
        return self._dict[key.lower()][1]

    def __delitem__(self, key):
        del self._dict[key.lower()]

    def __len__(self):
        return len(self._dict)

    def __iter__(self):
        return (k for k, v in self._dict.itervalues())

    def __eq__(self, value):
        return dict((k, v[1]) for k, v in self._dict.iteritems()) == \
            dict((k.lower(), v) for k, v in value.iteritems())
