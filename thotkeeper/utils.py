# ThotKeeper -- a personal daily journal application.
#
# Copyright (c) 2004-2024 C. Michael Pilato.  All rights reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE file which can be found at the top level of the ThotKeeper
# distribution.
#
# Website: https://github.com/cmpilato/thotkeeper

import requests
from requests.exceptions import HTTPError
from .version import (__version__, parse_version)


LATEST_VERSION_URL = 'https://raw.githubusercontent.com/cmpilato/thotkeeper/refs/heads/master/www/latest-version.json'

def update_check(update_url=LATEST_VERSION_URL):
    """Consult the contents of a web-accessible JSON file for the
    latest available version of ThotKeeper (and its download
    information).  Return a 2-tuple containing the new version and its
    download URL if there's an update available, or (None, None)
    otherwise."""

    # Try to fetch the contents of the URL, allowing for redirects.
    response = requests.get(update_url, allow_redirects=True)

    # Test how successful that fetch was.
    try:
        response.raise_for_status()
    except HTTPError as e:
        resp = e.response
        raise Exception(f'{resp.status_code} {resp.reason}') from e

    # Try to parse the response as JSON.
    try:
        contents = response.json()
        new_version = contents['version']
        update_url = contents['url']
    except Exception:
        raise Exception('Unable to parse JSON version information')

    # Compare versions
    new_version = parse_version(new_version)
    current_version = parse_version(__version__)
    if new_version > current_version:
        return '.'.join([str(x) for x in new_version]), None
    return None, None


def get_update_message(new_version, info_url):
    """Return a string suitable for notifying users about the status
    of their update check.  NEW_VERSION and INFO_URL generally come
    directly from a call to update_check()."""

    if new_version is None:
        return (f'You are running the latest version ({__version__}) '
                f'of ThotKeeper.')
    return (f'A new version ({new_version}) of ThotKeeper is available.\n'
            f'For more information, visit:\n{info_url}')
