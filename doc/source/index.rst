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

This is the core project for Brim.Net Python-based applications. It provides some reusable utility code and provides brimd, a launcher offering ease of deployment of WSGI applications (currently just using the Eventlet WSGI server) and maintaining background daemons. The brimd server will spawn subprocesses to handle requests and start daemons allowing for use of multiple CPU cores and for resiliency -- when a subprocess exits without being requested to, it will be restarted automatically.

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

* `Git <http://git-scm.com/>`_ since the code is hosted on `GitHub <http://github.com/gholt/brim>`_.
* `SetupTools <http://packages.python.org/distribute/>`_ for setup.py usage.
* `Nose <http://readthedocs.org/docs/nose/en/latest/>`_ for the test suite.
* `Coverage <http://nedbatchelder.com/code/coverage/>`_ to report on test coverage.
* `Sphinx <http://sphinx.pocoo.org/>`_ to build documentation.

Example Install on Ubuntu 10.04
-------------------------------
::

    $ sudo apt-get install gitcore python python-eventlet
    $ sudo easy_install setproctitle  # optional
    $ git clone git://github.com/gholt/brim
    $ cd brim
    $ sudo python setup.py install

Example Install for Build and Test on Ubuntu 10.04
--------------------------------------------------
::

    $ sudo apt-get install gitcore python python-setuptools python-nose \
      python-coverage python-sphinx python-eventlet python-simplejson
    $ sudo easy_install setproctitle
    $ git clone git://github.com/gholt/brim
    $ cd brim
    $ sudo python setup.py develop
    $ python setup.py build_sphinx
    $ ./.unittests


Usage Examples
==============


Example WSGI Usage
------------------

* Create /etc/brim/brimd.conf::

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

* Create /etc/brim/brimd.conf::

    [wsgi]
    apps = echo stats

    [wsgi]
    port = 81
    apps = echo2 stats

    [echo]
    call = brim.wsgi_echo.WSGIEcho

    [stats]
    call = brim.stats.Stats

    [echo2]
    call = brim.wsgi_echo.WSGIEcho
    path = /echo2

You can see the new section [brim2] that defines the second listening port with its own configuration of the echo app and the shared stats configuration.

* Start the server::

    $ sudo brimd start

* Access the "echo" app on the main port::

    $ curl -i http://127.0.0.1/echo --data-binary 'Just a test.'

* Access the "echo" app on the second port::

    $ curl -i http://127.0.0.1:81/echo2 --data-binary 'Just a test.'

* Note that the apps don't answer on the other ports::

    $ curl -i http://127.0.0.1/echo2 --data-binary 'Just a test.'
    $ curl -i http://127.0.0.1:81/echo --data-binary 'Just a test.'

* Access the "stats" app and see it's configured on both ports. You can perform extra requests on one port to ensure the stats returned are different::

    $ curl -s http://127.0.0.1/stats | python -mjson.tool
    $ curl -s http://127.0.0.1:81/stats | python -mjson.tool

* Stop the server::

    $ sudo brimd stop

The included brimd.conf-sample shows a full set of configuration options available for each subconfig and explains how the defaults usually fall back to the main conf.


Example TCP Straight Socket Application Usage
---------------------------------------------

TODO


Example UDP Application Usage
-----------------------------

TODO


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

Here's an example /etc/brim/brimd.conf with this app active::

    [brimd]
    wsgi = helloworld

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

    [brimd]
    wsgi = helloworld

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

So now, let's add the brim.stats.Stats app to our configuration so we'll be able to get a report on the server stats::

    [brimd]
    wsgi = helloworld stats

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
    "helloworld.last_called": 1326602976,
    "helloworld.requests": 1,
    ...
    "worker_0": {
        "helloworld.last_called": 1,
        "helloworld.requests": 1326602976,
    ...
    $ curl http://127.0.0.1/here
    Hello World!
    $ curl http://127.0.0.1/here
    Hello World!
    $ curl -s http://127.0.0.1/stats | python -mjson.tool
    ...
    "helloworld.last_called": 1326603159,
    "helloworld.requests": 3,
    ...
    "worker_0": {
        "helloworld.last_called": 3,
        "helloworld.requests": 1326603159,
    ...

Of course, we only have one worker so the overall stats just mirror that worker. You can add ``workers = <number>`` to your brimd.conf if you want more workers.

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

    [brim]
    wsgi = stats
    workers = 4

    [stats]
    call = brim.stats.Stats
    # path = <path>
    #   The request path to match and serve; any other paths will be passed on
    #   to the next WSGI app in the chain. This can serve as a basic
    #   restriction to accessing the stats by setting it to a hard to guess
    #   value. Default: /stats

After restarting the server, you can now access these stats::

    $ curl s- http://127.0.0.1/stats | python -mjson.tool
    {
        "request_count": 18317, 
        "start_time": 1326585797, 
        "status_2xx_count": 14326, 
        "status_3xx_count": 0, 
        "status_404_count": 3991, 
        "status_408_count": 0, 
        "status_499_count": 0, 
        "status_4xx_count": 3991, 
        "status_501_count": 0, 
        "status_5xx_count": 0, 
        "worker_0": {
            "request_count": 4698, 
            "start_time": 1326585797, 
            "status_2xx_count": 3742, 
            "status_3xx_count": 0, 
            "status_404_count": 956, 
            "status_408_count": 0, 
            "status_499_count": 0, 
            "status_4xx_count": 956, 
            "status_501_count": 0, 
            "status_5xx_count": 0
        }, 
        "worker_1": {
            "request_count": 4467, 
            "start_time": 1326585797, 
            "status_2xx_count": 3475, 
            "status_3xx_count": 0, 
            "status_404_count": 992, 
            "status_408_count": 0, 
            "status_499_count": 0, 
            "status_4xx_count": 992, 
            "status_501_count": 0, 
            "status_5xx_count": 0
        }, 
        "worker_2": {
            "request_count": 4497, 
            "start_time": 1326585797, 
            "status_2xx_count": 3505, 
            "status_3xx_count": 0, 
            "status_404_count": 992, 
            "status_408_count": 0, 
            "status_499_count": 0, 
            "status_4xx_count": 992, 
            "status_501_count": 0, 
            "status_5xx_count": 0
        }, 
        "worker_3": {
            "request_count": 4655, 
            "start_time": 1326585797, 
            "status_2xx_count": 3604, 
            "status_3xx_count": 0, 
            "status_404_count": 1051, 
            "status_408_count": 0, 
            "status_499_count": 0, 
            "status_4xx_count": 1051, 
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

TODO


UDP Socket Application Development
----------------------------------

TODO


Daemon Development
------------------

TODO


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
