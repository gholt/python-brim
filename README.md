# Brim.Net Utility Package

    Copyright 2012 Gregory Holt

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

## Overview

This is a project for providing general utility to Python programs.

For more in-depth documentation see <http://gholt.github.com/brim/>.

### Required Dependencies

The main code itself just requires Python 2 (2.6 or greater, not tested with
Python 3 yet).

### Optional Dependencies

* [Eventlet](http://eventlet.net/) green sockets can optionally be used by
  brim.service.get_listening_tcp_socket.

### Build and Test Dependencies

* [Git](http://git-scm.com/) since the code is hosted on
  [GitHub](http://github.com/gholt/brim).
* [SetupTools](http://packages.python.org/distribute/) for setup.py usage.
* [Nose](http://readthedocs.org/docs/nose/en/latest/) for the test suite.
* [Coverage](http://nedbatchelder.com/code/coverage/) to report on test
  coverage.
* [Sphinx](http://sphinx.pocoo.org/) to build documentation.

### Example Install on Ubuntu 10.04

    $ sudo apt-get install gitcore python
    $ sudo apt-get install python-eventlet  # optional
    $ git clone git://github.com/gholt/brim
    $ cd brim
    $ sudo python setup.py install

### Example Install for Build and Test on Ubuntu 10.04

    $ sudo apt-get install gitcore python python-setuptools python-nose \
      python-coverage python-sphinx python-eventlet
    $ git clone git://github.com/gholt/brim
    $ cd brim
    $ sudo python setup.py develop
    $ python setup.py build_sphinx
    $ ./.unittests
