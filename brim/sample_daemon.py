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
Contains a simple daemon that just logs a status line every so often.
This can be a good starting point for other daemons. See the source
for what's implemented and why.

See :py:func:`SampleDaemon.parse_conf` for configuration options.
"""

from time import time

from eventlet import sleep


class SampleDaemon(object):
    """
    A simple daemon that just logs a status line every so often. This
    can be a good starting point for other daemons. See the source
    for what's implemented and why.

    :param name: The name of the daemon, indicates the daemon's
                 section in the overall configuration for the WSGI
                 server.
    :param parsed_conf: The conf result from :py:func:`parse_conf`.
    """

    def __init__(self, name, parsed_conf):
        # Copy all items from the parsed_conf to actual instance attributes.
        for k, v in parsed_conf.iteritems():
            setattr(self, k, v)
        self.name = name

    def __call__(self, subserver, stats):
        """
        This sample daemon simply logs a status line every so often.

        This is the main entry point to the daemon. The brimd
        subserver will spawn a subprocess, create an instance of this
        daemon, and call this method. If the method exits for any
        reason, brimd will spawn a new subprocess, create a new
        daemon instance, and call this method again to ensure the
        daemon is always running.

        The stats object will have at least the stat variables asked
        for in :py:func:``stats_conf``. This stats object will
        support the following methods:

        get(<name>)

            Return the int value of the stat <name>.

        set(<name>, value)

            Sets the value of the stat <name>. The value will be
            treated as an unsigned integer.

        incr(<name>)

            Increments the value of the stat <name> by 1.


        :param subserver: The brim.server.Subserver that is managing
                          this daemon.
        :param stats: Shared memory statistics object as defined
                      above.
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
        """
        Translates the overall server configuration into an
        daemon-specific configuration dict suitable for passing as
        ``parsed_conf`` in the SampleDaemon constructor.

        Sample Configuration File::

            [sample_daemon]
            call = brim.sample_daemon.SampleDaemon
            # interval = <seconds>
            #   The number of seconds between each status line logged.
            #   Default: 60

        :param name: The name of the daemon, indicates the daemon's
                     section in the overall configuration for the
                     server.
        :param conf: The brim.conf.Conf instance representing the
                     overall configuration of the server.
        :returns: A dict suitable for passing as ``parsed_conf`` in
                  the SampleDaemon constructor.
        """
        return {'interval': conf.get_int(name, 'interval', 60)}

    @classmethod
    def stats_conf(cls, name, parsed_conf):
        """
        Returns a list of names that specifies the stat variables this app
        wants established.

        Retreiving stats can be accomplished through WSGI apps like
        brim.stats.Stats.

        :param name: The name of the app, indicates the app's section
                     in the overall configuration for the WSGI
                     server.
        :param parsed_conf: The conf result from
                            :py:func:`parse_conf`.
        """
        return ['iterations', 'last_run']
