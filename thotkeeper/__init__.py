# ThotKeeper -- a personal daily journal application.
#
# Copyright (c) 2004-2024 C. Michael Pilato.  All rights reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE file which can be found at the top level of the ThotKeeper
# distribution.
#
# Website: http://www.thotkeeper.org/

"""ThotKeeper is a cross-platform personal daily journaling program."""

import sys
from argparse import ArgumentParser
from .version import __version__


def main():
    epilog = (f'You are running ThotKeeper version {__version__}.  '
              f'See http://thotkeeper.org for more about this software.')
    parser = ArgumentParser(allow_abbrev=False,
                            description=__doc__,
                            epilog=epilog)
    parser.add_argument('--file',
                        metavar='FILE',
                        help='the name of the ThotKeeper diary file')
    parser.add_argument('--version',
                        action='store_true',
                        help='show version information')
    parser.add_argument('--update-check',
                        action='store_true',
                        help='check for a new version of ThotKeeper')
    args = parser.parse_args()

    # Just a version check?  No sweat.
    if args.version:
        print(__version__)
        return

    # Checking for new versions of ThotKeeper?  We can manage that.
    if args.update_check:
        from .utils import (get_update_message, update_check)
        try:
            print(get_update_message(*update_check()))
        except Exception as e:
            sys.stderr.write(f'Error occurred while checking for '
                             f'updates: {e}\n')
            sys.exit(1)
        return

    # If we get here, it's time to fire up the GUI application!
    from .app import ThotKeeper
    tk = ThotKeeper(args.file)
    tk.MainLoop()
    tk.OnExit()
