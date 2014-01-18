"""A simple daemon that just logs a status line every so often.

This can be a good starting point for other daemons. See the source for
what's implemented and why.

Configuration Options::

    [daemon_sample]
    call = brim.daemon_sample.DaemonSample
    # interval = <seconds>
    #   The number of seconds between each status line logged.
    #   Default: 60

Standard configuration options for all daemons are also supported. See
:ref:`brimd.conf-sample <brimdconfsample>` for more information.

Stats Variables:

==========  ======  ====================================================
Name        Type    Description
==========  ======  ====================================================
iterations  daemon  Number of times a status line has been logged.
last_run    daemon  Timestamp when the last status line was logged.
start_time  daemon  Timestamp when the daemon was started. If the daemon
                    had to be restarted, this timestamp will be updated
                    with the new start time. This item is available with
                    all daemons and set by the controlling
                    :py:class:`brim.server.Subserver`.
==========  ======  ====================================================
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
from time import time

from brim.server import sleep


class DaemonSample(object):
    """A simple daemon that just logs a status line every so often.

    :param name: The name of the daemon.
    :param parsed_conf: The result from parse_conf.
    """

    def __init__(self, name, parsed_conf):
        self.name = name
        """The name of the daemon."""
        self.interval = parsed_conf['interval']
        """The number of seconds between each status line logged."""

    def __call__(self, subserver, stats):
        """Logs a status line every so often.

        This is the main entry point to the daemon. The brimd subserver
        will spawn a subprocess, create an instance of this daemon, and
        call this method. If the method exits for any reason, brimd will
        spawn a new subprocess, create a new daemon instance, and call
        this method again to ensure the daemon is always running.

        The stats object will have at least the stat variables asked for
        in :py:meth:`stats_conf`. This stats object will support at
        least the following methods:

        ==================  ============================================
        get(name)           Returns the int value of the stat named.
        set(name, value)    Sets the value of the stat named. The value
                            will be treated as an unsigned integer.
        incr(name)          Increments the value of the stat named by 1.
        ==================  ============================================

        :param subserver: The :py:class:`brim.server.Subserver` that is
            managing this daemon.
        :param stats: The shared memory statistics object as defined
            above.
        :returns: Hopefully never. If the method does return, the caller
            should create a new daemon instance and call this method
            again.
        """
        iteration = 0
        while True:
            iteration += 1
            subserver.logger.info(
                '%s sample daemon log line %s' % (self.name, iteration))
            stats.set('last_run', time())
            stats.set('iterations', iteration)
            sleep(self.interval)

    @classmethod
    def parse_conf(cls, name, conf):
        """Translates the overall server configuration.

        The conf is translated into a daemon-specific configuration dict
        suitable for passing as ``parsed_conf`` in the
        :py:class:`DaemonSample` constructor.

        See the overall docs of :py:mod:`brim.daemon_sample` for
        configuration options.

        :param name: The name of the daemon, indicates the daemon's
            section in the overall configuration for the server.
        :param conf: The :py:class:`brim.conf.Conf` instance
            representing the overall configuration of the server.
        :returns: A dict suitable for passing as ``parsed_conf`` in the
            :py:class:`DaemonSample` constructor.
        """
        return {'interval': conf.get_int(name, 'interval', 60)}

    @classmethod
    def stats_conf(cls, name, parsed_conf):
        """Returns a list of (stat_name, stat_type) pairs.

        These pairs specify the stat variables this daemon wants
        established in the ``stats`` instance passed to
        :py:meth:`__call__`.

        Stats are often retrieved by users and utilities through WSGI
        apps like :py:class:`brim.wsgi_stats.WSGIStats`.

        See the overall docs of :py:mod:`brim.daemon_sample` for what
        stats are defined.

        The available stat_types are:

        ======  ========================================================
        daemon  Indicates a daemon only stat. No overall stat will be
                reported.
        sum     Indicates an overall stat should be reported that is a
                sum of the stat from all daemons.
        min     Indicates an overall stat should be reported that is the
                smallest value of the stat from all daemons.
        max     Indicates an overall stat should be reported that is the
                largest value of the stat from all daemons.
        ======  ========================================================

        :param name: The name of the daemon, indicates the daemon's
            section in the overall configuration for the daemon server.
        :param parsed_conf: The result from :py:meth:`parse_conf`.
        :returns: A list of (stat_name, stat_type) pairs.
        """
        return [('iterations', 'daemon'), ('last_run', 'daemon')]
