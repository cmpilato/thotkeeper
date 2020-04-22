# ThotKeeper -- a personal daily journal application.
#
# Copyright (c) 2004-2020 C. Michael Pilato.  All rights reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE file which can be found at the top level of the ThotKeeper
# distribution.
#
# Website: http://www.thotkeeper.org/


__version__ = "0.5.0-dev"


def parse_version(version):
    """Parse a version string, discarding any suffix and returning a
    3-tuple of the major, minor and patch version numbers."""

    import re
    match = re.search(r'^([0-9]+)\.([0-9]+)(\.([0-9]+))?', version)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2))
        try:
            patch = int(match.group(4))
        except Exception:
            patch = -1
        return [major, minor, patch]
    raise Exception(f'Invalid version string "{version}"')
