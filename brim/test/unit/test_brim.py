"""Tests for brim."""
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

from brim import __version__


class TestBrim(TestCase):

    def test_version(self):
        self.assertEqual(__version__.count('.'), 1)
        major, minor = __version__.split('.')
        major = int(major)
        self.assertEqual(len(minor), 2)
        minor = int(minor)


if __name__ == '__main__':
    main()
