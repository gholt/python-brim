# Brim.Net Core Package

    Copyright 2012 Gregory Holt
    Portions (httpform) Copyright 2011 OpenStack, LLC.

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

This is the core project for Brim.Net Python-based applications. It provides
some reusable utility code and provides brimd, a launcher offering ease of
deployment of WSGI applications (currently just using the Eventlet WSGI
server), straight TCP and UDP socket applications, and maintaining background
daemons.

For more in-depth documentation see <http://gholt.github.com/brim/>.

### Required Dependencies

* [Python >= 2.6](http://python.org/) Not tested with Python 3 yet.
* [Eventlet >= 0.9.16](http://eventlet.net/)
* Unix platform: This should run on any Unix platform, though only tested on
  Ubuntu 10.04 LTS to date.

### Optional Dependencies

* [SetProcTitle](http://code.google.com/p/py-setproctitle/) If this is
  installed, brimd will change its process titles to be more meaningful.
* [SimpleJSON](https://github.com/simplejson/simplejson) or other JSON library
  containing json.dumps and json.loads compatible functions. You can configure
  brimd to use these alternate libraries if you wish and complying apps and
  daemons will also use the alternate libraries.

### Build and Test Dependencies

* [Coverage](http://nedbatchelder.com/code/coverage/) to report on test
  coverage.
* [Git](http://git-scm.com/) since the code is hosted on
  [GitHub](http://github.com/gholt/brim).
* [Nose](http://readthedocs.org/docs/nose/en/latest/) for the test suite.
* [PIP](http://pypi.python.org/pypi/pip) to install additional Python packages.
* [Sphinx](http://sphinx.pocoo.org/) to build documentation.

### Example Install on Ubuntu 10.04

    $ sudo apt-get install git-core python python-pip
    $ sudo pip install eventlet
    $ sudo pip install setproctitle  # optional
    $ git clone git://github.com/gholt/brim
    $ cd brim
    $ sudo python setup.py install

### Example Install for Build and Test on Ubuntu 10.04

    $ sudo apt-get install git-core python python-coverage python-nose \
      python-pip python-simplejson python-sphinx
    $ sudo pip install eventlet
    $ sudo pip install setproctitle
    $ git clone git://github.com/gholt/brim
    $ cd brim
    $ sudo python setup.py develop
    $ python setup.py build_sphinx
    $ ./.unittests
