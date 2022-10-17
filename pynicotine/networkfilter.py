# Based on Nicotine+ code, but a slimmed-down and adjusted version of it

# COPYRIGHT (C) 2020-2022 Nicotine+ Contributors
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

from pynicotine import slskmessages


class NetworkFilter:
    """ Functions related to banning, blocking and ignoring users """

    def __init__(self, core, config, queue):

        self.core = core
        self.config = config
        self.queue = queue

        self.ipblock_requested = {}
        self.ipignore_requested = {}

    """ General """

    def _get_cached_user_ip(self, user, list_type):
        """ Retrieve the IP address of a user previously saved in a list. """

        if list_type == "block":
            ip_list = self.config.sections["server"]["ipblocklist"]
        else:
            ip_list = self.config.sections["server"]["ipignorelist"]

        for ip_address, username in ip_list.items():
            if user == username:
                return ip_address

        return None

    def _is_ip_in_list(self, address, list_type):
        """ Check if an IP address exists in a list, disregarding the username
        the address is paired with. """

        if address is None:
            return True

        if list_type == "block":
            ip_list = self.config.sections["server"]["ipblocklist"]
        else:
            ip_list = self.config.sections["server"]["ipignorelist"]

        s_address = address.split(".")

        for ip_address in ip_list:

            # No Wildcard in IP
            if "*" not in ip_address:
                if address == ip_address:
                    return True
                continue

            # Wildcard in IP
            parts = ip_address.split(".")
            seg = 0

            for part in parts:
                # Stop if there's no wildcard or matching string number
                if part not in (s_address[seg], "*"):
                    break

                seg += 1

                # Last time around
                if seg == 4:
                    # Wildcard blocked
                    return True

        # Not blocked
        return False

    def check_user(self, user, ip_address):
        """ Check if this user is banned, geoip-blocked, and which shares
        it is allowed to access based on transfer and shares settings. """

        if self.is_user_banned(user) or (ip_address is not None and self.is_ip_blocked(ip_address)):
            if self.config.sections["transfers"]["usecustomban"]:
                return 0, "Banned (%s)" % self.config.sections["transfers"]["customban"]

            return 0, "Banned"

        for row in self.config.sections["server"]["userlist"]:
            if row[0] != user:
                continue

            if self.config.sections["transfers"]["buddysharestrustedonly"] and not row[4]:
                # Only trusted buddies allowed, and user isn't trusted
                return 1, ""

            # For sending buddy-only shares
            return 2, ""

        return 1, ""

    def update_saved_user_ip_filters(self, user):
        """ When we know a user's IP address has changed, we call this function to
        update the IP saved in lists. """

        user_address = self.core.protothread.user_addresses.get(user)

        if not user_address:
            return

        new_ip, _new_port = user_address
        cached_blocked_ip = self.get_cached_blocked_user_ip(user)

        if cached_blocked_ip is not None and cached_blocked_ip != new_ip:
            self.unblock_user_ip(user)
            self.block_user_ip(user)

        cached_ignored_ip = self.get_cached_ignored_user_ip(user)

        if cached_ignored_ip is not None and cached_ignored_ip != new_ip:
            self.unignore_user_ip(user)
            self.ignore_user_ip(user)

    """ Banning """

    def ban_user(self, user):
        if self.is_user_banned(user):
            return
        self.core.transfers.ban_users({user})

    def block_user_ip(self, user):
        ip_address = self._add_user_ip_to_list(user, "block")
        if ip_address:
            self.queue.append(slskmessages.ConnCloseIP(ip_address))

    def unblock_user_ip(self, user):
        self._remove_user_ip_from_list(user, "block")

    def block_unblock_user_ip_callback(self, user):
        if user not in self.ipblock_requested:
            return False
        if self.ipblock_requested[user] == "remove":
            self.unblock_user_ip(user)
        else:
            self.block_user_ip(user)
        del self.ipblock_requested[user]
        return True

    def get_cached_blocked_user_ip(self, user):
        return self._get_cached_user_ip(user, "block")

    def is_user_banned(self, user):
        return user in self.config.sections["server"]["banlist"]

    def is_ip_blocked(self, address):
        return self._is_ip_in_list(address, "block")

    """ Ignoring """

    def ignore_unignore_user_ip_callback(self, user):
        if user not in self.ipignore_requested:
            return False
        if self.ipignore_requested[user] == "remove":
            self.unignore_user_ip(user)
        else:
            self.ignore_user_ip(user)
        del self.ipignore_requested[user]
        return True

    def get_cached_ignored_user_ip(self, user):
        return self._get_cached_user_ip(user, "ignore")

    def is_user_ignored(self, user):
        return user in self.config.sections["server"]["ignorelist"]

    def is_ip_ignored(self, address):
        return self._is_ip_in_list(address, "ignore")
