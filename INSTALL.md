Installing Thotkeeper
=====================

What You Need
-------------

To run ThotKeeper, you need a few bits of software.  Unfortunately,
this list may be incomplete, and we have no idea what versions of
anything are required.  Sorry 'bout that.  Anyway, here's the list:

   * Python 3.4 or newer [http://www.python.org]
     The Python programming language and interpreter.
      
   * wxPython 4.0.0 or newer [http://www.wxpython.org]
     Python interfaces to the wxWidgets cross-platform GUI library.

   * Requests [https://requests.readthedocs.io/en/master/]
     Python HTTP library (optional; used only by the feature
     that checks for new versions of ThotKeeper).


Installation
------------

ThotKeeper uses the standard Python setuptools for installation.
Simply explode the source distribution archive file on your system,
change your working directory to the top-level directory of the
exploded archive, and run:

    $ ./setup.py install

On a Unix system, you might need to do so as 'root'.  On Windows,
consider doing so using a command shell with elevated privileges ("Run
as Administrator").


Developing ThotKeeper
---------------------

ThotKeeper can generally be run directly from a checkout of its source
code tree.  Unix-like systems, you should be able to simply do:

    $ ./bin/thotkeeper

If that doesn't work, of you're not on a Unix-like system, try:

    $ python ./bin/thotkeeper

On Windows, you probably need to create a shortcut that invokes your
Python interpreter with the path of the 'thotkeeper' script as its
argument.  Or, if your Python interpreter can be found in the %PATH%
environment variable, you can run the following at a command prompt:

    C:\> python .\bin\thotkeeper


What If I Have Problems?
========================

Question, comments, and code contributions are always welcome at
http://www.thotkeeper.org/.
