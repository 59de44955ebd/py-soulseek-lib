# COPYRIGHT (C) 2020-2022 Nicotine+ Contributors
# COPYRIGHT (C) 2016-2017 Michael Labouebe <gfarmerfr@free.fr>
# COPYRIGHT (C) 2016-2018 Mutnick <mutnick@techie.com>
# COPYRIGHT (C) 2008-2011 Quinox <quinox@users.sf.net>
# COPYRIGHT (C) 2009 Hedonist <ak@sensi.org>
# COPYRIGHT (C) 2007 Gallows <g4ll0ws@gmail.com>
# COPYRIGHT (C) 2006-2009 Daelstorm <daelstorm@gmail.com>
# COPYRIGHT (C) 2003-2004 Hyriand <hyriand@thegraveyard.org>
# COPYRIGHT (C) 2001-2003 Alexander Kanavin
#
# GNU GENERAL PUBLIC LICENSE
#    Version 3, 29 June 2007
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
This module contains configuration classes for Nicotine.
"""

import configparser
import os
import sys

from ast import literal_eval
from collections import defaultdict


class Config:
    """
    This class holds configuration information and provides the
    following methods:

    need_config() - returns true if configuration information is incomplete
    read_config() - reads configuration information from file

    The actual configuration information is stored as a two-level dictionary.
    First-level keys are config sections, second-level keys are config
    parameters.
    """

    def __init__(self):
        self.application_name = "Nicotine+ Light"
        self.version = "1.0.0"
        self.python_version = sys.version

        self.config_loaded = False
        self.parser = configparser.ConfigParser(strict=False, interpolation=None)
        self.sections = defaultdict(dict)
        self.defaults = {}

    def load_config(self, filename, data_dir):
        from pynicotine.utils import load_file

        self.filename = filename
        self.data_dir = data_dir

        log_dir = os.path.join(self.data_dir, "logs")
        self.defaults = {
            "server": {
                "banlist": [],
                "ignorelist": [],
                "interface": "",
                "ipblocklist": {},
                "ipignorelist": {},
                "login": "",
                "passw": "",
                "portrange": (2234, 2239),
                "server": ("server.slsknet.org", 2242),
                "userlist": [],
            },
            "transfers": {
                "afterfinish": "",
                "afterfolder": "",
                "autoclear_downloads": False,
                "autoclear_uploads": False,
                "buddyshared": [],
                "buddysharestrustedonly": False,
                "customban": "Banned, don't bother retrying",
                "downloaddir": os.path.join(self.data_dir, 'downloads'),
                "downloadfilters": [
                    ["desktop.ini", 1],
                    ["folder.jpg", 1],
                    ["*.url", 1],
                    ["thumbs.db", 1],
                    ["albumart(_{........-....-....-....-............}_)?(_?(large|small))?\\.jpg", 0]
                ],
                "downloadlimit": 0,
                "downloadlimitalt": 100,
#                "downloadregexp": "",
                "enablefilters": False,
                "fifoqueue": False,
                "filelimit": 100,
                "friendsnolimits": False,
                "incompletedir": os.path.join(self.data_dir, 'incomplete'),
                "limitby": True,
                "lock": True,
                "preferfriends": False,
                "queuelimit": 10000,
                "remotedownloads": True,
                "rescanonstartup": True,
                "reverseorder": False,
                "shared": [],
                "sharedownloaddir": False,
                "uploadallowed": 2,
                "uploadbandwidth": 50,
                "uploaddir": os.path.join(self.data_dir, 'received'),
                "uploadlimit": 1000,
                "uploadlimitalt": 100,
                "uploadsinsubdirs": True,
                "uploadslots": 2,
                "usealtlimits": False,
                "usecustomban": False,
                "uselimit": False,
                "usernamesubfolders": False,
                "useupslots": False,
            },
            "searches": {
                "enablefilters": False,
                "maxresults": 150,
                "min_search_chars": 3,
                "private_search_results": True,
                "remove_special_chars": True,
                "search_results": True,
            },
            "logging": {
                "chatrooms": True,
                "debug": False,
                "debug_file_output": False,
                "debuglogsdir": os.path.join(log_dir, "debug"),
                "debugmodes": [],
                "log_timestamp": "%Y-%m-%d %H:%M:%S",
                "rooms": [],
                "transfers": False,
                "transferslogsdir": os.path.join(log_dir, "transfers"),
            },
        }

        # Initialize config with default values
        for key, value in self.defaults.items():
            self.sections[key] = value.copy()

        load_file(self.filename, self.parse_config)

        # Update config values from file
        self.set_config()

        # Allow relative pathes (=relative to config file!)
        config_dir = os.path.dirname(os.path.realpath(filename))
        for k in ["downloaddir", "incompletedir", "uploaddir"]:
            if self.sections["transfers"][k].startswith('.'):
                self.sections["transfers"][k] = os.path.join(config_dir, self.sections["transfers"][k][2:])

        shares = self.sections["transfers"]["shared"]
        for i in range(len(shares)):
            if shares[i][1].startswith('.'):
                shares[i] = (shares[i][0], os.path.join(config_dir, shares[i][1][2:]))

        # Convert special download folder share to regular share
        if self.sections["transfers"].get("sharedownloaddir", False):
            virtual_name = "Downloaded"
            shared_folder = (virtual_name, self.sections["transfers"]["downloaddir"])
            if shared_folder not in shares and virtual_name not in (x[0] for x in shares):
                shares.append(shared_folder)

        self.config_loaded = True

        from pynicotine.logfacility import log
        log.add_debug("Using configuration: %(file)s", {"file": self.filename})

    def parse_config(self, filename):
        """ Parses the config file """

        from pynicotine.utils import encode_path

        with open(encode_path(filename), 'a+', encoding="utf-8") as file_handle:
            file_handle.seek(0)
            self.parser.read_file(file_handle)

    def need_config(self):
        # Check if we have specified a username or password
        if not self.sections["server"]["login"] or not self.sections["server"]["passw"]:
            return True
        return False

    def set_config(self):
        """ Set config values parsed from file earlier """

        from pynicotine.logfacility import log

        for i in self.parser.sections():
            for j, val in self.parser.items(i, raw=True):

                # Check if config section exists in defaults
                if i not in self.defaults:  #  and i not in self.removed_options
                    log.add("Unknown config section '%s'", i)

                # Check if config option exists in defaults
                elif (j not in self.defaults.get(i, {})):  #  and i != "plugins" and j != "filter" and j not in self.removed_options.get(i, {})
                    log.add("Unknown config option '%(option)s' in section '%(section)s'",
                            {'option': j, 'section': i})

                else:
                    """ Attempt to get the default value for a config option. If there's no default
                    value, it's a custom option from a plugin, so no checks are needed. """

                    try:
                        default_val = self.defaults[i][j]

                    except KeyError:
                        try:
                            val = literal_eval(val)
                        except Exception:
                            pass

                        self.sections[i][j] = val
                        continue

                    """ Check that the value of a config option is of the same type as the default
                    value. If that's not the case, reset the value. """

                    try:
                        if not isinstance(default_val, str):
                            # Values are always read as strings, evaluate them if they aren't
                            # supposed to remain as strings
                            eval_val = literal_eval(val)

                        else:
                            eval_val = val

#                        if i != "plugins" and j != "filter":
                        if (isinstance(eval_val, type(default_val))
                                or (isinstance(default_val, bool)
                                    and isinstance(eval_val, int) and eval_val in (0, 1))):
                            # Value is valid
                            pass
                        else:
                            raise TypeError("Invalid config value type detected")

                        self.sections[i][j] = eval_val

                    except Exception:
                        # Value was unexpected, reset option
                        self.sections[i][j] = default_val

                        log.add("Config error: Couldn't decode '%s' section '%s' value '%s', value has been reset", (
                            (i[:120] + '…') if len(i) > 120 else i,
                            (j[:120] + '…') if len(j) > 120 else j,
                            (val[:120] + '…') if len(val) > 120 else val
                        ))

        server = self.sections["server"]

        # Check if server value is valid
        if (len(server["server"]) != 2
                or not isinstance(server["server"][0], str)
                or not isinstance(server["server"][1], int)):

            server["server"] = self.defaults["server"]["server"]

        # Check if port range value is valid
        if (len(server["portrange"]) != 2 or not all(isinstance(i, int) for i in server["portrange"])):
            server["portrange"] = self.defaults["server"]["portrange"]
        else:
            # Setting the port range in numerical order
            server["portrange"] = (min(server["portrange"]), max(server["portrange"]))

config = Config()
