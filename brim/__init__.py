"""The Brim.Net Core Package.

It provides some reusable utility code and provides brimd, a launcher
offering ease of deployment of WSGI applications (currently just using
the Eventlet WSGI server), straight TCP and UDP socket applications, and
maintaining background daemons.

==============================  ========================================
:py:mod:`brim`                  Just contains ``__version__``.
:py:mod:`brim.conf`             Provides a simple way to work with
                                configuration files.
:py:mod:`brim.daemon_sample`    A sample implementation of a daemon.
:py:mod:`brim.http`             Utilities for working with HTTP.
:py:mod:`brim.httpform`         Module for working with HTTP Form POSTs
                                iteratively.
:py:mod:`brim.log`              Logging utilities for brimd.
:py:mod:`brim.server`           The main module that implements the
                                Brim.Net Core Server.
:py:mod:`brim.service`          Provides functions useful for background
                                services.
:py:mod:`brim.tcp_echo`         A simple straight TCP socket
                                application.
:py:mod:`brim.udp_echo`         A simple straight UDP datagram
                                application.
:py:mod:`brim.util`             Miscellaneous classes and functions.
:py:mod:`brim.wsgi_basic_auth`  A WSGI application that offers Basic
                                Auth capabilities.
:py:mod:`brim.wsgi_echo`        A simple WSGI application that just
                                echoes the request body.
:py:mod:`brim.wsgi_fs`          A WSGI application that simply serves up
                                files from the file system.
:py:mod:`brim.wsgi_stats`       Reports the brimd server stats as a JSON
                                reponse.
==============================  ========================================
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

__version__ = '0.05'
"""The package version 'major.minor'.

It is an official release if the minor number is even; otherwise a
development release.
"""
