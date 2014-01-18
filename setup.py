#!/usr/bin/env python
"""Python setuptools Integration."""
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
from setuptools import find_packages, setup

from brim import __version__


setup(
    name='brim',
    version=__version__,
    description='Brim.Net Core Package',
    long_description="""
This is the core package for Brim.Net Python-based applications.

It provides some reusable utility code and provides brimd, a launcher
offering ease of deployment of WSGI applications (currently just
using the Eventlet WSGI server), straight TCP and UDP socket
applications, and maintaining background daemons.

Source code available at http://github.com/gholt/brim/

For more in-depth documentation see http://gholt.github.io/brim/

Note that if the minor version number is odd it is a release still
under development. An even number indicates a stable release.""",
    author='Gregory Holt',
    author_email='greg@brim.net',
    url='http://gholt.github.com/brim/',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
        'Topic :: Internet :: WWW/HTTP :: WSGI',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Middleware',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Server',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules'],
    requires=['eventlet(>=0.9.16)'],
    packages=find_packages(),
    entry_points={'console_scripts': ['brimd=brim.server:main']},
    test_suite='brim.test.unit',
    tests_require=['mock>=1.0.1'])
