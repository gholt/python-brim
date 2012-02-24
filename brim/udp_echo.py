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
Contains a simple straight UDP datagram application that just echoes
the incoming data back. This is a good starting point for other UDP
applications. See the source for what's implemented and why.

See :py:func:`UDPEcho.parse_conf` for configuration options.
"""


class UDPEcho(object):
    """
    A simple straight UDP datagram application that just echoes the
    incoming data back. This is a good starting point for other UDP
    applications. See the source for what's implemented and why.

    :param name: The name of the app, indicates the app's section in
                 the overall configuration for the server.
    :param parsed_conf: The conf result from :py:func:`parse_conf`.
    """

    def __init__(self, name, parsed_conf):
        # Copy all items from the parsed_conf to actual instance attributes.
        for k, v in parsed_conf.iteritems():
            setattr(self, k, v)
        self.name = name

    def __call__(self, subserver, stats, sock, datagram, ip, port):
        """
        Simply echo the incoming data back.

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
        :param datagram: The just received datagram.
        :param ip: The remote IP address.
        :param port: The remote IP port.
        """
        try:
            stats.set('byte_count', stats.get('byte_count') + len(datagram))
            sock.sendto(datagram, (ip, port))
        finally:
            subserver.logger.notice('served request of %s bytes from %s:%s' %
                                    (len(datagram), ip, port))

    @classmethod
    def parse_conf(cls, name, conf):
        """
        Translates the overall server configuration into an
        app-specific configuration dict suitable for passing as
        ``parsed_conf`` in the UDPEcho constructor.

        Sample Configuration File::

            [udp_echo]
            call = brim.udp_echo.UDPEcho

        :param name: The name of the app, indicates the app's section
                     in the overall configuration for the server.
        :param conf: The brim.conf.Conf instance representing the
                     overall configuration of the server.
        :returns: A dict suitable for passing as ``parsed_conf`` in
                  the UDPEcho constructor.
        """
        return {}

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
        return ['byte_count']
