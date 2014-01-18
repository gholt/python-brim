"""Contains a simple straight UDP datagram application.

The application just echoes any incoming data back. This is a good
starting point for other UDP applications. See the source for what's
implemented and why.

Configuration Options::

    [udp_echo]
    call = brim.udp_echo.UDPEcho

Standard configuration options for all UDP apps are also supported. See
:ref:`brimd.conf-sample <brimdconfsample>` for more information.

Stats Variables:

==============  ======  ================================================
Name            Type    Description
==============  ======  ================================================
byte_count      sum     Number of bytes read from clients.
datagram_count  sum     The number of datagrams received.
start_time      worker  Timestamp when the app was started. If the app
                        had to be restarted, this timestamp will be
                        updated with the new start time. This item is
                        available with all apps and set by the
                        controlling :py:class:`brim.server.Subserver`.
==============  ======  ================================================
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


class UDPEcho(object):
    """A simple straight UDP socket application.

    The application just echoes any incoming data back. This is a good
    starting point for other UDP applications. See the source for what's
    implemented and why.

    :param name: The name of the app.
    :param parsed_conf: The conf result from :py:meth:`parse_conf`.
    """

    def __init__(self, name, parsed_conf):
        self.name = name
        """The name of the app."""

    def __call__(self, subserver, stats, sock, datagram, ip, port):
        """Simply echo the incoming data back.

        This is the main entry point to the daemon. The brimd subserver
        will spawn a subprocess, listen on a UDP endpoint, create an
        instance of this app, and then call this method for each
        incoming datagram. If the app raises an Exception, a new
        instance of the app will be created and handed future
        datagrams.

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
            managing this app.
        :param stats: The shared memory statistics object as defined
            above.
        :param sock: The socket associated with the datagram; useful for
            replying back using sendto.
        :param datagram: The just received datagram.
        :param ip: The remote IP address.
        :param port: The remote IP port.
        """
        try:
            stats.set('byte_count', stats.get('byte_count') + len(datagram))
            sock.sendto(datagram, (ip, port))
        finally:
            subserver.logger.notice(
                'served request of %s bytes from %s:%s' %
                (len(datagram), ip, port))

    @classmethod
    def parse_conf(cls, name, conf):
        """Translates the overall server configuration.

        The conf is translated into a daemon-specific configuration dict
        suitable for passing as ``parsed_conf`` in the
        :py:class:`UDPEcho` constructor.

        See the overall docs of :py:mod:`brim.udp_echo` for
        configuration options.

        :param name: The name of the app, indicates the app's section in
            the overall configuration for the server.
        :param conf: The :py:class:`brim.conf.Conf` instance
            representing the overall configuration of the server.
        :returns: A dict suitable for passing as ``parsed_conf`` in the
            :py:class:`UDPEcho` constructor.
        """
        return {}

    @classmethod
    def stats_conf(cls, name, parsed_conf):
        """Returns a list of (stat_name, stat_type) pairs.

        These pairs specify the stat variables this app wants
        established in the ``stats`` instance passed to
        :py:meth:`__call__`.

        Stats are often retrieved by users and utilities through WSGI
        apps like :py:class:`brim.wsgi_stats.WSGIStats`.

        See the overall docs of :py:mod:`brim.udp_echo` for what
        stats are defined.

        The available stat_types are:

        ======  ========================================================
        worker  Indicates a worker only stat. No overall stat will be
                reported.
        sum     Indicates an overall stat should be reported that is a
                sum of the stat from all workers.
        min     Indicates an overall stat should be reported that is the
                smallest value of the stat from all workers.
        max     Indicates an overall stat should be reported that is the
                largest value of the stat from all workers.
        ======  ========================================================

        :param name: The name of the app, indicates the app's section in
            the overall configuration for the daemon server.
        :param parsed_conf: The result from :py:meth:`parse_conf`.
        :returns: A list of (stat_name, stat_type) pairs.
        """
        return [('byte_count', 'sum')]
