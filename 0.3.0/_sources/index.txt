Brim.Net Core Package
*********************

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

.. toctree::
   :maxdepth: 2

   license

Overview
========

.. warning::

    This is a prerelease version of this project. As such, even as the author I don't completely trust this code yet. It works for the specific cases I've tested, but it needs more use cases and time to prove itself reliable. If you find any problems or possible "oddities", please file issues on github: http://github.com/gholt/brim Thanks, and be careful!

This is the core project for Brim.Net Python-based applications. It provides some reusable utility code and provides brimd, a launcher offering ease of deployment of WSGI applications (currently just using the Eventlet WSGI server), straight TCP and UDP socket applications, and maintaining background daemons. The brimd server will spawn subprocesses to handle requests and start daemons allowing for use of multiple CPU cores and for resiliency -- when a subprocess exits without being requested to, it will be restarted automatically.

Required Dependencies
---------------------

* `Python >= 2.6 <http://python.org/>`_ Not tested with Python 3 yet.
* `Eventlet >= 0.9.16 <http://eventlet.net/>`_
* Unix platform: This should run on any Unix platform, though only tested on Ubuntu 10.04 LTS to date.

Optional Dependencies
---------------------

* `SetProcTitle <http://code.google.com/p/py-setproctitle/>`_ If this is installed, brimd will change its process titles to be more meaningful.
* `SimpleJSON <https://github.com/simplejson/simplejson>`_ or other JSON library containing json.dumps and json.loads compatible functions. You can configure brimd to use these alternate libraries if you wish and complying apps and daemons will also use the alternate libraries.

Build and Test Dependencies
---------------------------

* `Coverage <http://nedbatchelder.com/code/coverage/>`_ to report on test coverage.
* `Git <http://git-scm.com/>`_ since the code is hosted on `GitHub <http://github.com/gholt/brim>`_.
* `Nose <http://readthedocs.org/docs/nose/en/latest/>`_ for the test suite.
* `PIP <http://pypi.python.org/pypi/pip>`_ to install additional Python packages.
* `Sphinx <http://sphinx.pocoo.org/>`_ to build documentation.

Example Install on Ubuntu 10.04
-------------------------------
::

    $ sudo apt-get install git-core python python-pip
    $ sudo pip install eventlet
    $ sudo pip install setproctitle  # optional
    $ git clone git://github.com/gholt/brim
    $ cd brim
    $ sudo python setup.py install

Example Install for Build and Test on Ubuntu 10.04
--------------------------------------------------
::

    $ sudo apt-get install git-core python python-coverage python-nose \
      python-pip python-simplejson
    $ sudo pip install eventlet
    $ sudo pip install setproctitle
    $ sudo pip install sphinx
    $ git clone git://github.com/gholt/brim
    $ cd brim
    $ sudo python setup.py develop
    $ python setup.py build_sphinx
    $ ./.unittests


Usage Examples
==============


Example WSGI Usage
------------------

* Create /etc/brimd.conf::

    [wsgi]
    apps = echo stats

    [echo]
    call = brim.wsgi_echo.WSGIEcho

    [stats]
    call = brim.stats.Stats

* Start the server::

    $ sudo brimd start

* Access the "echo" app (echos *Just a test.* back)::

    $ curl -i http://127.0.0.1/echo --data-binary 'Just a test.'

* Access a non-existent path (404s)::

    $ curl -i http://127.0.0.1/invalid

* Access the "stats" app (returns JSON formatted server stats)::

    $ curl -s http://127.0.0.1/stats | python -mjson.tool

* Stop the server::

    $ sudo brimd stop

Run ``brimd -h`` for more details on server control. It supports the standard init.d-style commands as well a special no-daemon mode for debugging.

Also, see the included brimd.conf-sample for a full set of configuration options available, such as the ip and port to use, number of subprocesses (workers), the user/group to run as, subdaemons to start, etc.


Example WSGI Multi-Configuration Usage
--------------------------------------

You can even set up multiple listening address or ports and control them with a single brimd, if you want. This can also be achieved with separate conf files and the -c and -p command line options to brimd, but most should find it easier to have one configuration with additional subconfigs. For example:

* Create /etc/brimd.conf::

    [wsgi]
    apps = echo stats

    [wsgi2]
    port = 81
    apps = echo2 stats

    [echo]
    call = brim.wsgi_echo.WSGIEcho

    [stats]
    call = brim.stats.Stats

    [echo2]
    call = brim.wsgi_echo.WSGIEcho
    path = /echo2

You can see the new section [wsgi2] that defines the second listening port with its own configuration of the echo app and the shared stats configuration.

* Start the server::

    $ sudo brimd start

* Access the "echo" app on the main port::

    $ curl -i http://127.0.0.1/echo --data-binary 'Just a test.'

* Access the "echo" app on the second port::

    $ curl -i http://127.0.0.1:81/echo2 --data-binary 'Just a test.'

* Note that the apps don't answer on the other ports::

    $ curl -i http://127.0.0.1/echo2 --data-binary 'Just a test.'
    $ curl -i http://127.0.0.1:81/echo --data-binary 'Just a test.'

* Access the "stats" app and see it's configured on both ports::

    $ curl -s http://127.0.0.1/stats | python -mjson.tool
    $ curl -s http://127.0.0.1:81/stats | python -mjson.tool

* Stop the server::

    $ sudo brimd stop

The included brimd.conf-sample shows a full set of configuration options available for each subconfig and explains how the defaults usually fall back to the main conf.


Example TCP Straight Socket Application Usage
---------------------------------------------

* Create /etc/brimd.conf::

    [tcp]
    call = brim.tcp_echo.TCPEcho

* Start the server::

    $ sudo brimd start

* Access the "echo" app (echos *Just a test.* back)::

    $ echo 'Just a test.' | nc -q 2 127.0.0.1 80

* Stop the server::

    $ sudo brimd stop

* Create a multi-port /etc/brimd.conf::

    [tcp]
    call = brim.tcp_echo.TCPEcho

    [tcp2]
    call = brim.tcp_echo.TCPEcho
    port = 81

* Start the server::

    $ sudo brimd start

* Access the "echo" apps (echo *Just a test.* back)::

    $ echo 'Just a test.' | nc -q 2 127.0.0.1 80
    $ echo 'Just a test.' | nc -q 2 127.0.0.1 81

* Stop the server::

    $ sudo brimd stop

The included brimd.conf-sample shows a full set of configuration options available for each subconfig and explains how the defaults usually fall back to the main conf.


Example UDP Application Usage
-----------------------------

* Create /etc/brimd.conf::

    [udp]
    call = brim.udp_echo.UDPEcho

* Start the server::

    $ sudo brimd start

* Access the "echo" app (echos *Just a test.* back)::

    $ echo 'Just a test.' | nc -q 2 -u 127.0.0.1 80

* Stop the server::

    $ sudo brimd stop

* Create a multi-port /etc/brimd.conf::

    [udp]
    call = brim.udp_echo.UDPEcho

    [udp2]
    call = brim.udp_echo.UDPEcho
    port = 81

* Start the server::

    $ sudo brimd start

* Access the "echo" apps (echo *Just a test.* back)::

    $ echo 'Just a test.' | nc -q 2 -u 127.0.0.1 80
    $ echo 'Just a test.' | nc -q 2 -u 127.0.0.1 81

* Stop the server::

    $ sudo brimd stop

The included brimd.conf-sample shows a full set of configuration options available for each subconfig and explains how the defaults usually fall back to the main conf.


Example Daemon Usage
--------------------

The brimd server can manage additional daemons as well as the main WSGI server. You configure them much like WSGI apps, but with the daemons configuration value. There is a brim.daemon_sample.DaemonSample that can be a good start for writing new daemons.

Here's an example brimd.conf that starts the sample daemon::

    [daemons]
    daemons = sample

    [sample]
    call = brim.daemon_sample.DaemonSample


Development Examples
====================


WSGI Application Development
----------------------------

Developing WSGI applications for brimd is quite similar to other Python WSGI servers. Here's a simple example::

    class HelloWorld(object):

        def __init__(self, name, conf, next_app):
            self.next_app = next_app

        def __call__(self, env, start_response):
            if env['PATH_INFO'] != '/helloworld':
                return self.next_app(env, start_response)
            body = 'Hello World!\n'
            start_response('200 OK', [('Content-Length', str(len(body)))])
            return body

Here's an example /etc/brimd.conf with this app active::

    [wsgi]
    apps = helloworld

    [helloworld]
    call = mypackage.mymodule.HelloWorld

We can then start the server and access the new app::

    $ sudo brimd restart
    $ curl -i http://127.0.0.1/helloworld
    HTTP/1.1 200 OK
    Content-Length: 13
    Date: Sat, 14 Jan 2012 22:57:38 GMT

    Hello World!

The ``__call__`` method is the usual WSGI (env, start_response) call made per incoming request.

The ``__init__`` is a little different for brimd and takes the name of the app as configured in the brimd.conf file, the full brimd configuration object as an instance of brim.conf.Conf, and the next WSGI app in the chain (the last app in the chain will always be brimd itself).

The name lets you know which part of the conf to access for any app-specific configuration, though you can always stray outside just that section if needed.

The conf, while by default is the full server brim.conf.Conf instance, it can be pre-parsed if desired. This is useful if you want to raise an exception if the configuration is invalid, preventing the server from starting with an explanatory message. Otherwise, once your app's ``__init__`` method is called, you should not raise any exceptions unless something goes horribly wrong, as brimd will just keep restarting your app to try to keep it running.

To pre-parse the configuration, you just add a class method of parse_conf that takes the brim.conf.Conf instance and returns whatever you want as the conf argument to your constructor. To continue our example, we'll look for a path in the config and exit if it doesn't exist::

    class HelloWorld(object):

        def __init__(self, name, conf, next_app):
            # conf is what was returned from parse_conf now.
            self.path = conf
            self.next_app = next_app

        def __call__(self, env, start_response):
            if env['PATH_INFO'] != self.path:
                return self.next_app(env, start_response)
            body = 'Hello World!\n'
            start_response('200 OK', [('Content-Length', str(len(body)))])
            return body

        @classmethod
        def parse_conf(cls, name, conf):
            path = conf.get(name, 'path')
            if not path:
                raise Exception('[%s] you must configure a path to serve.' % name)
            return path

Now, let's restart the server without yet updating the config and see what happens::

    $ sudo brimd restart
    [helloworld] you must configure a path to serve.

It's important to note that this early config parsing is done in the main server process before any subprocesses are launched. Anything loaded into memory will copied into the subprocesses' memory as well. So, to reiterate, ``parse_conf`` is called in the main process and ``__init__`` is called in each subprocess.

Now, let's update our configuration::

    [wsgi]
    apps = helloworld

    [helloworld]
    call = mypackage.mymodule.HelloWorld
    path = /here

And now try using our app again::

    $ sudo brimd restart
    $ curl -i http://127.0.0.1/here
    HTTP/1.1 200 OK
    Content-Length: 13
    Date: Sat, 14 Jan 2012 23:05:20 GMT

    Hello World!

To continue our example, let's add stats to our application. We'll count how many times we're called and the last time we were called::

    from time import time


    class HelloWorld(object):

        def __init__(self, name, conf, next_app):
            self.name = name
            self.path = conf
            self.next_app = next_app

        def __call__(self, env, start_response):
            if env['PATH_INFO'] != self.path:
                return self.next_app(env, start_response)
            # Here's where we update the stats.
            env['brim.stats'].incr('%s.requests' % self.name)
            env['brim.stats'].set('%s.last_called' % self.name, time())
            body = 'Hello World!\n'
            start_response('200 OK', [('Content-Length', str(len(body)))])
            return body

        @classmethod
        def parse_conf(cls, name, conf):
            path = conf.get(name, 'path')
            if not path:
                raise Exception('[%s] you must configure a path to serve.' % name)
            return path

        @classmethod
        def stats_conf(cls, name, conf):
            # This is the new class method to configure additional stats, it
            # returns a list of (stat_name, stat_type) tuples.
            return [('%s.requests' % name, 'sum'),
                    ('%s.last_called' % name, 'max')]

You can see that we configure the stats with the new stats_conf class method. The method returns a list of (stat_name, stat_type) pairs. stat_name is the str name of the stat and stat_type is one of the following:

    worker

        Indicates a worker only stat. No overall stat will be reported.

    sum

        Indicates an overall stat should be reported that is a sum of the stat from all workers.

    min

        Indicates an overall stat should be reported that is the smallest value of the stat from all workers.

    max

        Indicates an overall stat should be reported that is the largest value of the stat from all workers.

When handling actual requests, we can access the stats via the ``env['brim.stats']`` object, which supports the following methods:

        get(<name>)

            Return the int value of the stat <name>.

        set(<name>, value)

            Sets the value of the stat <name>. The value will be treated as an unsigned integer.


        incr(<name>)

            Increments the value of the stat <name> by 1.

So now, let's add the brim.stats.Stats app to our configuration so we'll be able to get a report on the server stats; we'll also set up two workers to show the separate worker stats::

    [wsgi]
    apps = helloworld stats
    workers = 2

    [helloworld]
    call = mypackage.mymodule.HelloWorld
    path = /here

    [stats]
    call = brim.stats.Stats

Let's try it out::

    $ sudo brimd restart
    $ curl http://127.0.0.1/here
    Hello World!
    $ curl -s http://127.0.0.1/stats | python -mjson.tool
    ...
        "wsgi": {
            "0": {
                "helloworld.last_called": 0, 
                "helloworld.requests": 0, 
    ...
            "1": {
                "helloworld.last_called": 1330399869, 
                "helloworld.requests": 1, 
    ...
            "helloworld.last_called": 1330399869, 
            "helloworld.requests": 1, 
    ...
    $ curl http://127.0.0.1/here
    Hello World!
    $ curl http://127.0.0.1/here
    Hello World!
    $ curl -s http://127.0.0.1/stats | python -mjson.tool
    ...
        "wsgi": {
            "0": {
                "helloworld.last_called": 0, 
                "helloworld.requests": 0, 
    ...
            "1": {
                "helloworld.last_called": 1330399935, 
                "helloworld.requests": 3, 
    ...
            "helloworld.last_called": 1330399935, 
            "helloworld.requests": 3, 
    ...

With very low load, a single worker often gets all the requests. If you have Apache Bench installed you might try that to get a better load test::

    $ ab -n 12345 http://127.0.0.1/here
    ...
    $ curl -s http://127.0.0.1/stats | python -mjson.tool
    ...
        "wsgi": {
            "0": {
                "helloworld.last_called": 1330399999, 
                "helloworld.requests": 6201, 
    ...
            "1": {
                "helloworld.last_called": 1330399999, 
                "helloworld.requests": 6147, 
    ...
            "helloworld.last_called": 1330399999, 
            "helloworld.requests": 12348, 
    ...


Extra WSGI env Items
....................

brim

    This is the brim.server.Server instance itself. Normally you don't need access to this, but some apps like brim.stats.Stats do.

brim.start

    The time.time() the request started processing.

brim.logger

    A logging.Logger instance for most logging needs. This logger can be configured in brimd.conf and by default it logs at the INFO level and above to syslog's LOCAL0 facility. Note that the server automatically logs request/responses at the NOTICE level, so you don't have to.

brim.txn

    A uuid.uuid4().hex value to unique identify the request. This can be very useful when logging so that you can track what a request is doing on a busy server. This is automatically added to every log line the brim.logger logs.

brim.additional_request_log_info

    A list of strings that will be appended to the request log line that brimd generates. This can be useful for identifying requests or what actions requests may have taken.

    It's usually best to add your app's info all at once with a prefix word, like:

    ``env['brim.additional_request_log_info'].extend(['myapp:', 'myinfo1', 'myinfo2'])``

    You could just add it all as one word ``.append('myapp: myinfo1 myinfo2')`` but understand that this will encode the spaces to %20 on the log line.

brim.stats

    An object that gives access to server stats. Which stats are available is determined by the server configuration, and specifically by each app's stats_conf class method. See the brim.wsgi_echo.WSGIEcho and brim.stats.Stats apps for examples of how to use these stats. This stats object will implement the following methods:

        get(<name>)

            Return the int value of the stat <name>.

        set(<name>, int)

            Sets the in value of the stat <name>. The value will be treated as unsigned.

        incr(<name>)

            Increments the value of the stat <name> by 1.

| brim.json_dumps
| brim.json_loads

    These are the JSON dumps and loads functions for converting to and from JSON and Python objects. By default, these are json.dumps and json.loads, but faster libraries are out there and can be configured in brimd.conf. Using these env items means you'll automatically use whatever is configured.


Server Stats
............

The brimd server tracks various statistics, such as the server start time and number of requests processed. The brim.stats.Stats app can be configured to provide access to these stats via a JSON response::

    [wsgi]
    apps = stats
    workers = 2

    [stats]
    call = brim.stats.Stats
    # path = <path>
    #   The request path to match and serve; any other paths will be passed on
    #   to the next WSGI app in the chain. This can serve as a basic
    #   restriction to accessing the stats by setting it to a hard to guess
    #   value. Default: /stats

After restarting the server, you can now access these stats::

    $ curl -s http://127.0.0.1/stats | python -mjson.tool
    {
        "start_time": 1330395908,
        "wsgi": {
            "0": {
                "request_count": 29243,
                "start_time": 1330395908,
                "status_2xx_count": 22995,
                "status_3xx_count": 0,
                "status_404_count": 0,
                "status_408_count": 0,
                "status_499_count": 0,
                "status_4xx_count": 6248,
                "status_501_count": 0,
                "status_5xx_count": 0
            },
            "1": {
                "request_count": 29453,
                "start_time": 1330395908,
                "status_2xx_count": 23358,
                "status_3xx_count": 0,
                "status_404_count": 0,
                "status_408_count": 0,
                "status_499_count": 0,
                "status_4xx_count": 6095,
                "status_501_count": 0,
                "status_5xx_count": 0
            },
            "request_count": 58696,
            "status_2xx_count": 46353,
            "status_3xx_count": 0,
            "status_404_count": 0,
            "status_408_count": 0,
            "status_499_count": 0,
            "status_4xx_count": 12343,
            "status_501_count": 0,
            "status_5xx_count": 0
        }
    }

Notice there are overall server stats and individual worker stats. Here is what's available by default (apps can configure additional stats):

request_count

    This is the number of requests served by the server and is simply a sum of all the worker's request_counts.

start_time

    This is the int(time.time()) the server was started. Each worker also has a start_time that indicates when that subprocess was started. If a subprocess crashes and restarts, this start_time will be different than the overall server start_time.

| status_2xx_count
| status_3xx_count
| status_4xx_count
| status_5xx_count

    These are the counts of requests that returned the response code ranges stated. For example, a high status_5xx_count can indicate a major server problem.

| status_404_count
| status_408_count
| etc.

    These track specific response codes. Which response codes are tracked can be configured in brimd.conf, but are 404, 408, 499, and 501 by default. A high 404 count on a server that normally shouldn't do so can indicate missing files or a bad incoming link. 408 Request Timeout and 499 Disconnect can indicate network problems or perhaps too aggressive timeouts. 501 Not Implemented counts can often be subtracted from the status_5xx_count to get a true count of real server problems.


TCP Straight Socket Application Development
-------------------------------------------

Developing brimd straight TCP socket applications is very simple::

    class HelloWorld(object):

        def __init__(self, name, conf):
            self.name = name

        def __call__(self, subserver, stats, sock, ip, port):
            sock.send('Hello World!\n')
            sock.close()

You'd probably want a lot of error checking in your call, but this works for now. So let's set up an /etc/brimd.conf to run this application::

    [tcp]
    call = mypackage.mymodule.HelloWorld

We can then start the server and access the new app::

    $ sudo brimd restart
    $ nc -q 2 127.0.0.1 80
    Hello World!

The ``__call__`` method is called for each incoming connection with the subserver, stats, socket, ip, and port of the connection. The subserver is the brim.server.TCPSubserver that accepted the request; usually you just use the logger attribute of this class. The stats will be explained a bit further down. The socket, ip, and port represent the just established TCP connection.

The ``__init__`` takes the name of the app as configured in the brimd.conf file, and the full brimd configuration object as an instance of brim.conf.Conf.

The name lets you know which part of the conf to access for any app-specific configuration, though you can always stray outside just that section if needed.

The conf, while by default is the full server brim.conf.Conf instance, it can be pre-parsed if desired. This is useful if you want to raise an exception if the configuration is invalid, preventing the server from starting with an explanatory message. Otherwise, once your app's ``__init__`` method is called, you should not raise any exceptions unless something goes horribly wrong, as brimd will just keep restarting your app to try to keep it running.

To pre-parse the configuration, you just add a class method of parse_conf that takes the brim.conf.Conf instance and returns whatever you want as the conf argument to your constructor. To continue our example, we'll look for a message in the config and exit if it doesn't exist::

    class HelloWorld(object):

        def __init__(self, name, conf):
            # conf is what was returned from parse_conf now.
            self.message = conf
            self.name = name

        def __call__(self, subserver, stats, sock, ip, port):
            sock.send(self.message + '\n')
            sock.close()

        @classmethod
        def parse_conf(cls, name, conf):
            message = conf.get(name, 'message')
            if not message:
                raise Exception('[%s] you must configure a message to serve.' %
                                name)
            return message

Now, let's restart the server without yet updating the config and see what happens::

    $ sudo brimd restart
    [tcp] you must configure a message to serve.

It's important to note that this early config parsing is done in the main server process before any subprocesses are launched. Anything loaded into memory will copied into the subprocesses' memory as well. So, to reiterate, ``parse_conf`` is called in the main process and ``__init__`` is called in each subprocess.

Now, let's update our configuration::

    [tcp]
    call = mypackage.mymodule.HelloWorld
    message = Hello, hello!

And now try using our app again::

    $ sudo brimd restart
    $ nc -q 2 127.0.0.1 80
    Hello, hello!

To continue our example, let's add stats to our application. We'll count how many times we're called and the last time we were called::

    from time import time


    class HelloWorld(object):

        def __init__(self, name, conf):
            # conf is what was returned from parse_conf now.
            self.message = conf
            self.name = name

        def __call__(self, subserver, stats, sock, ip, port):
            sock.send(self.message + '\n')
            sock.close()
            # Here's where we update the stats.
            stats.incr('%s.connections' % self.name)
            stats.set('%s.last_called' % self.name, time())

        @classmethod
        def parse_conf(cls, name, conf):
            message = conf.get(name, 'message')
            if not message:
                raise Exception('[%s] you must configure a message to serve.' %
                                name)
            return message

        @classmethod
        def stats_conf(cls, name, conf):
            # This is the new class method to configure additional stats, it
            # returns a list of (stat_name, stat_type) tuples.
            return [('%s.connections' % name, 'sum'),
                    ('%s.last_called' % name, 'max')]

You can see that we configure the stats with the new stats_conf class method. The method returns a list of (stat_name, stat_type) pairs. stat_name is the str name of the stat and stat_type is one of the following:

    worker

        Indicates a worker only stat. No overall stat will be reported.

    sum

        Indicates an overall stat should be reported that is a sum of the stat from all workers.

    min

        Indicates an overall stat should be reported that is the smallest value of the stat from all workers.

    max

        Indicates an overall stat should be reported that is the largest value of the stat from all workers.

When handling actual requests, we can access the stats via the passed stats object, which supports the following methods:

        get(<name>)

            Return the int value of the stat <name>.

        set(<name>, value)

            Sets the value of the stat <name>. The value will be treated as an unsigned integer.


        incr(<name>)

            Increments the value of the stat <name> by 1.

So now, let's add the brim.stats.Stats WSGI app to our configuration so we'll be able to get a report on the server stats; we'll also set up two workers to show the separate worker stats::

    [tcp]
    call = mypackage.mymodule.HelloWorld
    message = Hello, hello!
    workers = 2

    [wsgi]
    apps = stats
    port = 81

    [stats]
    call = brim.stats.Stats

Let's try it out::

    $ sudo brimd restart
    $ nc -q 2 127.0.0.1 80
    Hello, hello!
    $ curl -s http://127.0.0.1:81/stats | python -mjson.tool
    ...
        "tcp": {
            "0": {
    ...
                "tcp.connections": 1, 
                "tcp.last_called": 1330399433
    ...
            "1": {
    ...
                "tcp.connections": 0, 
                "tcp.last_called": 0
    ...
            "tcp.connections": 1, 
            "tcp.last_called": 1330399433
    ...
    $ nc -q 2 127.0.0.1 80
    Hello, hello!
    $ nc -q 2 127.0.0.1 80
    Hello, hello!
    $ curl -s http://127.0.0.1:81/stats | python -mjson.tool
    ...
        "tcp": {
            "0": {
    ...
                "tcp.connections": 3, 
                "tcp.last_called": 1330399486
    ...
            "1": {
    ...
                "tcp.connections": 0, 
                "tcp.last_called": 0
    ...
            "tcp.connections": 3, 
            "tcp.last_called": 1330399486
    ...

With very low load, a single worker often gets all the requests. You might try a simple for loop to try to generate some load::

    $ for x in {1..1234}; do nc 127.0.0.1 80; done > /dev/null
    $ curl -s http://127.0.0.1:81/stats | python -mjson.tool
    ...
        "tcp": {
            "0": {
    ...
                "tcp.connections": 692, 
                "tcp.last_called": 1330399723
    ...
            "1": {
    ...
                "tcp.connections": 545, 
                "tcp.last_called": 1330399723
    ...
            "tcp.connections": 1237, 
            "tcp.last_called": 1330399723
    ...


UDP Socket Application Development
----------------------------------

Developing brimd UDP socket applications is also very simple::

    class HelloWorld(object):

        def __init__(self, name, conf):
            self.name = name

        def __call__(self, subserver, stats, sock, datagram, ip, port):
            sock.sendto('Hello World!\n', (ip, port))

You'd probably want a lot of error checking in your call, but this works for now. So let's set up an /etc/brimd.conf to run this application::

    [udp]
    call = mypackage.mymodule.HelloWorld

We can then start the server and access the new app::

    $ sudo brimd restart
    $ echo 'test' | nc -u -q 2 127.0.0.1 80
    Hello World!

The ``__call__`` method is called for each incoming datagram with the subserver, stats, datagram, socket, ip, and port of the datagram. The subserver is the brim.server.UDPSubserver that accepted the request; usually you just use the logger attribute of this class. The stats will be explained a bit further down. The socket, ip, and port represent the just received datagram. The datagram is the payload of the UDP packet received.

The ``__init__`` takes the name of the app as configured in the brimd.conf file, and the full brimd configuration object as an instance of brim.conf.Conf.

The name lets you know which part of the conf to access for any app-specific configuration, though you can always stray outside just that section if needed.

The conf, while by default is the full server brim.conf.Conf instance, it can be pre-parsed if desired. This is useful if you want to raise an exception if the configuration is invalid, preventing the server from starting with an explanatory message. Otherwise, once your app's ``__init__`` method is called, you should not raise any exceptions unless something goes horribly wrong, as brimd will just keep restarting your app to try to keep it running.

To pre-parse the configuration, you just add a class method of parse_conf that takes the brim.conf.Conf instance and returns whatever you want as the conf argument to your constructor. To continue our example, we'll look for a message in the config and exit if it doesn't exist::

    class HelloWorld(object):

        def __init__(self, name, conf):
            # conf is what was returned from parse_conf now.
            self.message = conf
            self.name = name

        def __call__(self, subserver, stats, sock, datagram, ip, port):
            sock.sendto(self.message + '\n', (ip, port))

        @classmethod
        def parse_conf(cls, name, conf):
            message = conf.get(name, 'message')
            if not message:
                raise Exception('[%s] you must configure a message to serve.' %
                                name)
            return message

Now, let's restart the server without yet updating the config and see what happens::

    $ sudo brimd restart
    [udp] you must configure a message to serve.

It's important to note that this early config parsing is done in the main server process before any subprocesses are launched. Anything loaded into memory will copied into the subprocesses' memory as well. So, to reiterate, ``parse_conf`` is called in the main process and ``__init__`` is called in each subprocess.

Now, let's update our configuration::

    [udp]
    call = mypackage.mymodule.HelloWorld
    message = Hello, hello!

And now try using our app again::

    $ sudo brimd restart
    $ echo 'test' | nc -u -q 2 127.0.0.1 80
    Hello, hello!

To continue our example, let's add stats to our application. We'll record the last time we were called::

    from time import time


    class HelloWorld(object):

        def __init__(self, name, conf):
            # conf is what was returned from parse_conf now.
            self.message = conf
            self.name = name

        def __call__(self, subserver, stats, sock, datagram, ip, port):
            sock.sendto(self.message + '\n', (ip, port))
            # Here's where we update the stats.
            stats.set('last_called', time())

        @classmethod
        def parse_conf(cls, name, conf):
            message = conf.get(name, 'message')
            if not message:
                raise Exception('[%s] you must configure a message to serve.' %
                                name)
            return message

        @classmethod
        def stats_conf(cls, name, conf):
            # This is the new class method to configure additional stats, it
            # returns a list of names of stats to allow. Since UDP doesn't
            # support multiple workers, there's no need for the stat types like
            # WSGI and TCP applications.
            return ['last_called']

You can see that we configure the stats with the new stats_conf class method. The method returns a list of names of stats to enable.

When handling actual requests, we can access the stats via the passed stats object, which supports the following methods:

        get(<name>)

            Return the int value of the stat <name>.

        set(<name>, value)

            Sets the value of the stat <name>. The value will be treated as an unsigned integer.


        incr(<name>)

            Increments the value of the stat <name> by 1.

So now, let's add the brim.stats.Stats WSGI app to our configuration so we'll be able to get a report on the server stats::

    [udp]
    call = mypackage.mymodule.HelloWorld
    message = Hello, hello!

    [wsgi]
    apps = stats
    port = 81

    [stats]
    call = brim.stats.Stats

Let's try it out::

    $ sudo brimd restart
    $ echo 'test' | nc -u -q 2 127.0.0.1 80
    Hello, hello!
    $ curl -s http://127.0.0.1:81/stats | python -mjson.tool
    ...
        "udp": {
    ...
            "last_called": 1330401361, 
    ...


Daemon Development
------------------

Daemons for brimd are simply background processes you'd like brimd to ensure are running. If the daemon exits, it'll just be restarted automatically. Developing daemons is quite simple::

    from time import sleep


    class HelloWorld(object):

        def __init__(self, name, conf):
            self.name = name

        def __call__(self, subserver, stats):
            line = 0
            while True:
                line += 1
                subserver.logger.info('sample log line %s' % line)
                sleep(60)

So let's set up an /etc/brimd.conf to run this daemon::

    [daemons]
    daemons = helloworld

    [helloworld]
    call = mypackage.mymodule.HelloWorld

We can then start the server and monitor syslog to see the lines logged::

    $ sudo brimd restart
    $ sudo tail -F /var/log/syslog
    Feb 27 20:16:08 lucid brimdaemons sample log line 1
    ...

The ``__call__`` method is called to start the daemon subprocess with the subserver and stats object to use. The subserver is the brim.server.DaemonsSubserver that started the subprocess; usually you just use the logger attribute of this class. The stats will be explained a bit further down.

The ``__init__`` takes the name of the daemon as configured in the brimd.conf file, and the full brimd configuration object as an instance of brim.conf.Conf.

The name lets you know which part of the conf to access for any daemon-specific configuration, though you can always stray outside just that section if needed.

The conf, while by default is the full server brim.conf.Conf instance, it can be pre-parsed if desired. This is useful if you want to raise an exception if the configuration is invalid, preventing the server from starting with an explanatory message. Otherwise, once your daemon's ``__init__`` method is called, you should not raise any exceptions unless something goes horribly wrong, as brimd will just keep restarting your daemon to try to keep it running.

To pre-parse the configuration, you just add a class method of parse_conf that takes the brim.conf.Conf instance and returns whatever you want as the conf argument to your constructor. To continue our example, we'll look for a message in the config and exit if it doesn't exist::

    from time import sleep


    class HelloWorld(object):

        def __init__(self, name, conf):
            # conf is what was returned from parse_conf now.
            self.message = conf
            self.name = name

        def __call__(self, subserver, stats):
            line = 0
            while True:
                line += 1
                subserver.logger.info('%s %s' % (self.message, line))
                sleep(60)

        @classmethod
        def parse_conf(cls, name, conf):
            message = conf.get(name, 'message')
            if not message:
                raise Exception('[%s] you must configure a message to log.' %
                                name)
            return message

Now, let's restart the server without yet updating the config and see what happens::

    $ sudo brimd restart
    [helloworld] you must configure a message to log.

It's important to note that this early config parsing is done in the main server process before any subprocesses are launched. Anything loaded into memory will copied into the subprocesses' memory as well. So, to reiterate, ``parse_conf`` is called in the main process and ``__init__`` is called in each subprocess.

Now, let's update our configuration::

    [daemons]
    daemons = helloworld

    [helloworld]
    call = mypackage.mymodule.HelloWorld
    message = Hello, hello!

And now try running our daemon again::

    $ sudo brimd restart
    $ sudo tail -F /var/log/syslog
    Feb 27 20:17:11 lucid brimdaemons Hello, hello! 1
    ...

To continue our example, let's add stats to our daemon. We'll record the last time we logged::

    from time import sleep, time


    class HelloWorld(object):

        def __init__(self, name, conf):
            # conf is what was returned from parse_conf now.
            self.message = conf
            self.name = name

        def __call__(self, subserver, stats):
            line = 0
            while True:
                line += 1
                subserver.logger.info('%s %s' % (self.message, line))
                # Here's where we update the stats.
                stats.set('last_logged', time())
                sleep(60)

        @classmethod
        def parse_conf(cls, name, conf):
            message = conf.get(name, 'message')
            if not message:
                raise Exception('[%s] you must configure a message to log.' %
                                name)
            return message

        @classmethod
        def stats_conf(cls, name, conf):
            # This is the new class method to configure additional stats, it
            # returns a list of names of stats to allow. Since daemons don't
            # have multiple workers, there's no need for the stat types like
            # WSGI and TCP applications.
            return ['last_logged']

You can see that we configure the stats with the new stats_conf class method. The method returns a list of names of stats to enable.

When handling actual requests, we can access the stats via the passed stats object, which supports the following methods:

        get(<name>)

            Return the int value of the stat <name>.

        set(<name>, value)

            Sets the value of the stat <name>. The value will be treated as an unsigned integer.


        incr(<name>)

            Increments the value of the stat <name> by 1.

So now, let's add the brim.stats.Stats WSGI app to our configuration so we'll be able to get a report on the server stats::

    [daemons]
    daemons = helloworld

    [helloworld]
    call = mypackage.mymodule.HelloWorld
    message = Hello, hello!

    [wsgi]
    apps = stats
    port = 81

    [stats]
    call = brim.stats.Stats

Let's try it out::

    $ sudo brimd restart
    $ sudo tail -F /var/log/syslog
    Feb 27 20:18:33 lucid brimdaemons Hello, hello! 1
    ...
    $ curl -s http://127.0.0.1:81/stats | python -mjson.tool
    ...
        "daemons": {
            "last_logged": 1330402713, 
    ...


Code-Generated Documentation
============================

.. toctree::
    :maxdepth: 2

    brim

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
