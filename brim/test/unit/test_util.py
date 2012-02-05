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

from brim import util


class TestLockPath(TestCase):

    def setUp(self):
        self.orig_os_open = util.os_open
        self.orig_time = util.time
        self.orig_flock = util.flock
        self.orig_sleep = util.sleep
        self.orig_os_close = util.os_close
        self.os_open_calls = []
        self.time_calls = []
        self.flock_calls = []
        self.sleep_calls = []
        self.os_close_calls = []

        def _os_open(*args):
            self.os_open_calls.append(args)
            return len(self.os_open_calls)

        def _time(*args):
            self.time_calls.append(args)
            return len(self.time_calls)

        util.os_open = _os_open
        util.time = _time
        util.flock = lambda *a: self.flock_calls.append(a)
        util.sleep = lambda *a: self.sleep_calls.append(a)
        util.os_close = lambda *a: self.os_close_calls.append(a)

    def tearDown(self):
        util.os_open = self.orig_os_open
        util.time = self.orig_time
        util.flock = self.orig_flock
        util.sleep = self.orig_sleep
        util.os_close = self.orig_os_close

    def test_lock_path(self):
        inwith = False
        with util.lock_path('test', 15):
            inwith = True
        self.assertTrue(inwith)
        self.assertEquals(self.os_open_calls, [('test', 0)])
        self.assertEquals(self.flock_calls, [(1, util.LOCK_EX | util.LOCK_NB)])
        self.assertEquals(self.sleep_calls, [])
        self.assertEquals(self.os_close_calls, [(1,)])

    def test_lock_path_time_delay(self):
        flock_calls = []

        def _flock(*args):
            flock_calls.append(args)
            if len(flock_calls) == 1:
                err = IOError('testing')
                err.errno = util.EAGAIN
                raise err

        util.flock = _flock
        inwith = False
        with util.lock_path('test', 15):
            inwith = True
        self.assertTrue(inwith)
        self.assertEquals(self.os_open_calls, [('test', 0)])
        self.assertEquals(flock_calls, [(1, util.LOCK_EX | util.LOCK_NB)] * 2)
        self.assertEquals(self.sleep_calls, [(0.01,)])
        self.assertEquals(self.os_close_calls, [(1,)])

    def test_lock_path_timeout(self):
        flock_calls = []

        def _flock(*args):
            flock_calls.append(args)
            err = IOError('testing')
            err.errno = util.EAGAIN
            raise err

        util.flock = _flock
        inwith = False
        try:
            with util.lock_path('test', 15):
                inwith = True
        except Exception, err:
            exc = err
        self.assertFalse(inwith)
        self.assertTrue(isinstance(exc, util.LockPathTimeout))
        self.assertEquals(str(exc), "Timeout 15s trying to lock 'test'.")
        self.assertEquals(self.os_open_calls, [('test', 0)])
        self.assertEquals(flock_calls, [(1, util.LOCK_EX | util.LOCK_NB)] * 15)
        self.assertEquals(self.sleep_calls, [(0.01,)] * 15)
        self.assertEquals(self.os_close_calls, [(1,)])

    def test_lock_path_other_exception(self):
        flock_calls = []

        def _flock(*args):
            flock_calls.append(args)
            raise IOError('testing')

        util.flock = _flock
        inwith = False
        try:
            with util.lock_path('test', 15):
                inwith = True
        except Exception, err:
            exc = err
        self.assertFalse(inwith)
        self.assertTrue(isinstance(exc, IOError))
        self.assertEquals(str(exc), 'testing')
        self.assertEquals(self.os_open_calls, [('test', 0)])
        self.assertEquals(flock_calls, [(1, util.LOCK_EX | util.LOCK_NB)])
        self.assertEquals(self.sleep_calls, [])
        self.assertEquals(self.os_close_calls, [(1,)])


class TestMakeDirs(TestCase):

    def setUp(self):
        self.orig_exists = util.exists
        self.orig_makedirs = util.makedirs
        self.exists_calls = []
        self.makedirs_calls = []

        def _exists(*args):
            self.exists_calls.append(args)
            return False

        util.exists = _exists
        util.makedirs = lambda *a: self.makedirs_calls.append(a)

    def tearDown(self):
        util.exists = self.orig_exists
        util.makedirs = self.orig_makedirs

    def test_make_dirs(self):
        util.make_dirs('test')
        self.assertEquals(self.exists_calls, [('test',)])
        self.assertEquals(self.makedirs_calls, [('test', 0777)])

    def test_make_dirs_exists(self):
        exists_calls = []

        def _exists(*args):
            exists_calls.append(args)
            return True

        util.exists = _exists
        util.make_dirs('test')
        self.assertEquals(exists_calls, [('test',)])
        self.assertEquals(self.makedirs_calls, [])

    def test_make_dirs_did_not_exist_but_then_did(self):
        makedirs_calls = []

        def _makedirs(*args):
            makedirs_calls.append(args)
            err = OSError('testing')
            err.errno = util.EEXIST
            raise err

        util.makedirs = _makedirs
        util.make_dirs('test')
        self.assertEquals(self.exists_calls, [('test',)])
        self.assertEquals(makedirs_calls, [('test', 0777)])

    def test_make_dirs_other_error(self):
        makedirs_calls = []

        def _makedirs(*args):
            makedirs_calls.append(args)
            raise OSError('testing')

        util.makedirs = _makedirs
        exc = None
        try:
            util.make_dirs('test')
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), 'testing')
        self.assertEquals(self.exists_calls, [('test',)])
        self.assertEquals(makedirs_calls, [('test', 0777)])


class TestUnlink(TestCase):

    def setUp(self):
        self.orig_os_unlink = util.os_unlink
        self.os_unlink_calls = []
        util.os_unlink = lambda *a: self.os_unlink_calls.append(a)

    def tearDown(self):
        util.os_unlink = self.orig_os_unlink

    def test_unlink(self):
        util.unlink('test')
        self.assertEquals(self.os_unlink_calls, [('test',)])

    def test_unlink_already_gone(self):
        os_unlink_calls = []

        def _os_unlink(*args):
            os_unlink_calls.append(args)
            err = OSError('testing')
            err.errno = util.ENOENT
            raise err

        util.os_unlink = _os_unlink
        util.unlink('test')
        self.assertEquals(os_unlink_calls, [('test',)])

    def test_unlink_other_error(self):
        os_unlink_calls = []

        def _os_unlink(*args):
            os_unlink_calls.append(args)
            raise OSError('testing')

        util.os_unlink = _os_unlink
        exc = None
        try:
            util.unlink('test')
        except Exception, err:
            exc = err
        self.assertEquals(str(exc), 'testing')
        self.assertEquals(os_unlink_calls, [('test',)])


if __name__ == '__main__':
    main()
