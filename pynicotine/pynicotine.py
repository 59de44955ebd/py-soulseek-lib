# Based on Nicotine+ code, but a slimmed-down and adjusted version of it

# COPYRIGHT (C) 2020-2022 Nicotine+ Contributors
# COPYRIGHT (C) 2020-2022 Mathias <mail@mathias.is>
# COPYRIGHT (C) 2016-2017 Michael Labouebe <gfarmerfr@free.fr>
# COPYRIGHT (C) 2016 Mutnick <muhing@yahoo.com>
# COPYRIGHT (C) 2013 eL_vErDe <gandalf@le-vert.net>
# COPYRIGHT (C) 2008-2012 Quinox <quinox@users.sf.net>
# COPYRIGHT (C) 2009 Hedonist <ak@sensi.org>
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
This is the actual client code. Actual GUI classes are in the separate modules
"""

import os
import signal
import sys

from collections import deque

from pynicotine import slskmessages
from pynicotine import slskproto
from pynicotine.config import config
from pynicotine.logfacility import log
from pynicotine.networkfilter import NetworkFilter
from pynicotine.search import Search
from pynicotine.shares import Shares
from pynicotine.slskmessages import LoginFailure
from pynicotine.slskmessages import UserStatus
from pynicotine.transfers import Transfers
from pynicotine.emitter import EventEmitter


class NicotineCore(EventEmitter):
    """ NicotineCore contains handlers for various messages from the networking thread.
    This class links the networking thread and user interface. """

    def __init__(self, bindip, port):
        super().__init__()

        self.network_callback = None

        self.network_filter = None
        self.shares = None
        self.search = None
        self.transfers = None
        self.protothread = None

        self.bindip = bindip
        self.port = port

        self.shutdown = False
        self.away = False
        self.logged_in = False
        self.login_username = None  # Only present while logged in
        self.user_ip_address = None
        self.privileges_left = 0  # None

        self.events = {}
        self.queue = deque()
        self.user_statuses = {}
        self.watched_users = set()
        self.ip_requested = set()

    """ Actions """

    def start(self, network_callback):

        self.network_callback = network_callback

        script_dir = os.path.dirname(__file__)
        log.add("Loading %(program)s %(version)s", {"program": "Python", "version": config.python_version})
        log.add_debug("Using %(program)s executable: %(exe)s", {"program": "Python", "exe": str(sys.executable)})
        log.add_debug("Using %(program)s executable: %(exe)s", {"program": config.application_name, "exe": script_dir})
        log.add("Loading %(program)s %(version)s", {"program": config.application_name, "version": config.version})

        self.protothread = slskproto.SlskProtoThread(
            core_callback=self.network_callback, queue=self.queue, bindip=self.bindip, port=self.port,
            interface=config.sections["server"]["interface"],
            port_range=config.sections["server"]["portrange"]
        )
        self.protothread.start()

        self.network_filter = NetworkFilter(self, config, self.queue)
        self.shares = Shares(self, config, self.queue, self.network_callback)
        self.search = Search(self, config, self.queue, self.shares.share_dbs)
        self.transfers = Transfers(self, config, self.queue, self.network_callback)

        self.transfers.init_transfers()

        # Callback handlers for messages
        self.events = {
            slskmessages.AddUser: self.add_user,
            slskmessages.AdminMessage: self.admin_message,
            slskmessages.ChangePassword: self.change_password,
            slskmessages.CheckDownloadQueue: self.transfers.check_download_queue_callback,
            slskmessages.CheckUploadQueue: self.transfers.check_upload_queue_callback,
            slskmessages.ConnectToPeer: self.connect_to_peer,
            slskmessages.DistribSearch: self.search.distrib_search,
            slskmessages.DownloadConnClose: self.transfers.download_conn_close,
            slskmessages.DownloadFile: self.transfers.file_download,
            slskmessages.DownloadFileError: self.transfers.download_file_error,
            slskmessages.FileDownloadInit: self.transfers.file_download_init,
            slskmessages.FileSearch: self.search.search_request,
            slskmessages.FileSearchResult: self.search.file_search_result,
            slskmessages.FileUploadInit: self.transfers.file_upload_init,
            slskmessages.FolderContentsRequest: self.shares.folder_contents_request,
            slskmessages.FolderContentsResponse: self.transfers.folder_contents_response,
            slskmessages.GetPeerAddress: self.get_peer_address,
            slskmessages.GetSharedFileList: self.shares.get_shared_file_list,
            slskmessages.GetUserStats: self.get_user_stats,
            slskmessages.GetUserStatus: self.get_user_status,
            slskmessages.Login: self.login,
            slskmessages.PlaceInQueue: self.transfers.place_in_queue,
            slskmessages.PlaceInQueueRequest: self.transfers.place_in_queue_request,
            slskmessages.QueueUpload: self.transfers.queue_upload,
            slskmessages.RoomSearch: self.search.search_request,
            slskmessages.ServerDisconnect: self.server_disconnect,
            slskmessages.ServerTimeout: self.server_timeout,
            slskmessages.SetConnectionStats: self.set_connection_stats,
            slskmessages.ShowConnectionErrorMessage: self.show_connection_error_message,
            slskmessages.TransferRequest: self.transfers.transfer_request,
            slskmessages.TransferResponse: self.transfers.transfer_response,
            slskmessages.TransferTimeout: self.transfers.transfer_timeout,
            slskmessages.UploadConnClose: self.transfers.upload_conn_close,
            slskmessages.UploadDenied: self.transfers.upload_denied,
            slskmessages.UploadFailed: self.transfers.upload_failed,
            slskmessages.UploadFile: self.transfers.file_upload,
            slskmessages.UploadFileError: self.transfers.upload_file_error,
            slskmessages.UserSearch: self.search.search_request,

            # ignored
            slskmessages.AckNotifyPrivileges: self.dummy_message,
            slskmessages.AddToPrivileged: self.dummy_message,
            slskmessages.CantConnectToPeer: self.dummy_message,
            slskmessages.CantCreateRoom: self.dummy_message,
            slskmessages.CheckPrivileges: self.dummy_message,
            slskmessages.DistribAlive: self.dummy_message,
            slskmessages.DistribAliveInterval: self.dummy_message,
            slskmessages.DistribBranchLevel: self.dummy_message,
            slskmessages.DistribBranchRoot: self.dummy_message,
            slskmessages.DistribChildDepth: self.dummy_message,
            slskmessages.ExactFileSearch: self.dummy_message,
            slskmessages.FileSearchRequest: self.dummy_message,
            slskmessages.GlobalRecommendations: self.dummy_message,
            slskmessages.GlobalUserList: self.dummy_message,
            slskmessages.ItemRecommendations: self.dummy_message,
            slskmessages.ItemSimilarUsers: self.dummy_message,
            slskmessages.JoinRoom: self.dummy_message,
            slskmessages.LeaveRoom: self.dummy_message,
            slskmessages.MessageProgress: self.dummy_message,
            slskmessages.MessageUser: self.dummy_message,
            slskmessages.MinParentsInCache: self.dummy_message,
            slskmessages.NotifyPrivileges: self.dummy_message,
            slskmessages.ParentInactivityTimeout: self.dummy_message,
            slskmessages.ParentMinSpeed: self.dummy_message,
            slskmessages.ParentSpeedRatio: self.dummy_message,
            slskmessages.PeerInit: self.dummy_message,
            slskmessages.PierceFireWall: self.dummy_message,
            slskmessages.PlaceholdUpload: self.dummy_message,
            slskmessages.PMessageUser: self.dummy_message,
            slskmessages.PossibleParents: self.dummy_message,
            slskmessages.PrivateRoomAdded: self.dummy_message,
            slskmessages.PrivateRoomAddOperator: self.dummy_message,
            slskmessages.PrivateRoomAddUser: self.dummy_message,
            slskmessages.PrivateRoomDisown: self.dummy_message,
            slskmessages.PrivateRoomOperatorAdded: self.dummy_message,
            slskmessages.PrivateRoomOperatorRemoved: self.dummy_message,
            slskmessages.PrivateRoomOwned: self.dummy_message,
            slskmessages.PrivateRoomRemoved: self.dummy_message,
            slskmessages.PrivateRoomRemoveOperator: self.dummy_message,
            slskmessages.PrivateRoomRemoveUser: self.dummy_message,
            slskmessages.PrivateRoomSomething: self.dummy_message,
            slskmessages.PrivateRoomToggle: self.dummy_message,
            slskmessages.PrivateRoomUsers: self.dummy_message,
            slskmessages.PrivilegedUsers: self.dummy_message,
            slskmessages.PublicRoomMessage: self.dummy_message,
            slskmessages.QueuedDownloads: self.dummy_message,
            slskmessages.Recommendations: self.dummy_message,
            slskmessages.RelatedSearch: self.dummy_message,
            slskmessages.Relogged: self.dummy_message,
            slskmessages.ResetDistributed: self.dummy_message,
            slskmessages.RoomAdded: self.dummy_message,
            slskmessages.RoomList: self.dummy_message,
            slskmessages.RoomRemoved: self.dummy_message,
            slskmessages.RoomTickerAdd: self.dummy_message,
            slskmessages.RoomTickerRemove: self.dummy_message,
            slskmessages.RoomTickerState: self.dummy_message,
            slskmessages.SayChatroom: self.dummy_message,
            slskmessages.SearchInactivityTimeout: self.dummy_message,
            slskmessages.ServerPing: self.dummy_message,
            slskmessages.SharedFileList: self.dummy_message,
            slskmessages.SimilarUsers: self.dummy_message,
            slskmessages.TunneledMessage: self.dummy_message,
            slskmessages.UnknownPeerMessage: self.dummy_message,
            slskmessages.UploadQueueNotification: self.dummy_message,
            slskmessages.UserInfoReply: self.dummy_message,
            slskmessages.UserInfoRequest: self.dummy_message,
            slskmessages.UserInterests: self.dummy_message,
            slskmessages.UserJoinedRoom: self.dummy_message,
            slskmessages.UserLeftRoom: self.dummy_message,
            slskmessages.UserPrivileged: self.dummy_message,
            slskmessages.WishlistInterval: self.dummy_message,
        }

    def quit(self, signal_type=None, _frame=None):

        log.add("Quitting %(program)s %(version)s, %(status)s…", {
            "program": config.application_name,
            "version": config.version,
            "status": "terminating" if signal_type == signal.SIGTERM else "application closing"
        })

        # Indicate that a shutdown has started, to prevent UI callbacks from networking thread
        self.shutdown = True

        # Shut down networking thread
        if self.protothread:
            self.protothread.abort()

        # Save download/upload list to file
        if self.transfers:
            self.transfers.quit()

        # Closing up all shelves db
        if self.shares:
            self.shares.quit()

        self.emit('quit')

        log.add("Quit %(program)s %(version)s, %(status)s!", {
            "program": config.application_name,
            "version": config.version,
            "status": "terminated" if signal_type == signal.SIGTERM else "done"
        })
        log.close_log_files()

    def connect(self):

        if not self.protothread.server_disconnected:
            return True

        if config.need_config():
            log.add("You need to specify a username and password before connecting…")
            self.emit('setup')
            return False

        valid_network_interface = self.protothread.validate_network_interface()

        if not valid_network_interface:
            message = (
                "The network interface you specified, '%s', does not exist. Change or remove the specified "
                "network interface and restart Nicotine+.")
            log.add_important_error(message, self.protothread.interface)
            return False

        valid_listen_port = self.protothread.validate_listen_port()

        if not valid_listen_port:
            message = (
                "The range you specified for client connection ports was "
                "{}-{}, but none of these were usable. Increase and/or ".format(self.protothread.portrange[0],
                                                                                self.protothread.portrange[1])
                + "move the range and restart Nicotine+.")
            if self.protothread.portrange[0] < 1024:
                message += "\n\n" + (
                    "Note that part of your range lies below 1024, this is usually not allowed on"
                    " most operating systems with the exception of Windows.")

            log.add_important_error(message)
            return False

        # Clear any potential messages queued up while offline
        self.queue.clear()

        addr = config.sections["server"]["server"]
        login = config.sections["server"]["login"]
        password = config.sections["server"]["passw"]

        self.protothread.server_disconnected = False
        self.queue.append(slskmessages.ServerConnect(addr, login=(login, password)))
        return True

    def disconnect(self):
        self.queue.append(slskmessages.ServerDisconnect())

    def send_message_to_peer(self, user, message, address=None):
        """ Sends message to a peer. Used when we know the username of a peer,
        but don't have/know an active connection. """

        self.queue.append(slskmessages.SendNetworkMessage(user, message, address))

    def request_change_password(self, password):
        self.queue.append(slskmessages.ChangePassword(password))

    def request_ip_address(self, username):
        self.ip_requested.add(username)
        self.queue.append(slskmessages.GetPeerAddress(username))

    def request_set_status(self, status):
        self.queue.append(slskmessages.SetStatus(status))

    def watch_user(self, user, force_update=False):
        """ Tell the server we want to be notified of status/stat updates
        for a user """

        if not self.logged_in:
            return

        if not force_update and user in self.watched_users:
            # Already being watched, and we don't need to re-fetch the status/stats
            return

        self.queue.append(slskmessages.AddUser(user))

        # Get privilege status
        self.queue.append(slskmessages.GetUserStatus(user))

        self.watched_users.add(user)

    """ Network Events """

    def network_event(self, msgs):
        for msg in msgs:
            if self.shutdown:
                return
            try:
                self.events[msg.__class__](msg)
            except KeyError:
#                log.add("No handler for class %s %s", (msg.__class__, dir(msg)))
                pass
        msgs.clear()

    @staticmethod
    def dummy_message(msg):
        # Ignore received message
        pass

    def show_connection_error_message(self, msg):
        """ Request UI to show error messages related to connectivity """

        for i in msg.msgs:
            if i.__class__ in (slskmessages.TransferRequest, slskmessages.FileUploadInit):
                self.transfers.get_cant_connect_upload(msg.user, i.token)

            elif i.__class__ is slskmessages.QueueUpload:
                self.transfers.get_cant_connect_queue_file(msg.user, i.file)

            elif i.__class__ is slskmessages.GetSharedFileList:
                self.userbrowse.show_connection_error(msg.user)

    def server_timeout(self, _msg):
        if not config.need_config():
            self.connect()

    def server_disconnect(self, msg=None):
        self.logged_in = False

        # Clean up connections
        self.user_statuses.clear()
        self.watched_users.clear()

        self.transfers.server_disconnect()

        self.emit('server_disconnect')

        self.login_username = None

    def set_connection_stats(self, msg):
        self.emit('set_connection_stats', msg)

    def login(self, msg):
        """ Server code: 1 """

        if msg.success:
            self.logged_in = True
            self.login_username = msg.username

            self.watch_user(msg.username)

            if msg.ip_address is not None:
                self.user_ip_address = msg.ip_address

            self.transfers.server_login()

            self.emit('server_login')

            if msg.banner:
                log.add(msg.banner)

            self.shares.send_num_shared_folders_files()
#            self.queue.append(slskmessages.PrivateRoomToggle(config.sections["server"]["private_chatrooms"]))

        else:
            if msg.reason == LoginFailure.PASSWORD:
                self.emit('invalid_password')
                return

            log.add_important_error("Unable to connect to the server. Reason: %s", msg.reason)

    def get_peer_address(self, msg):
        """ Server code: 3 """

        user = msg.user

        # User seems to be offline, don't update IP
        if msg.ip_address != "0.0.0.0":

            # If the IP address changed, make sure our IP block/ignore list reflects this
            self.network_filter.update_saved_user_ip_filters(user)

            if self.network_filter.block_unblock_user_ip_callback(user):
                return

            if self.network_filter.ignore_unignore_user_ip_callback(user):
                return

        if user not in self.ip_requested:
            return

        self.ip_requested.remove(user)

        if msg.ip_address == "0.0.0.0":
            log.add("Cannot retrieve the IP of user %s, since this user is offline", user)
            return

        log.add("IP address of user %(user)s is %(ip)s, port %(port)i%(country)s", {
            'user': user,
            'ip': msg.ip_address,
            'port': msg.port,
        })

    def add_user(self, msg):
        """ Server code: 5 """

        if msg.userexists:
            self.get_user_stats(msg)
            return

        # User does not exist, server will not keep us informed if the user is created later
        self.watched_users.discard(msg.user)

    def get_user_status(self, msg):
        """ Server code: 7 """

        user = msg.user
        status = msg.status
        privileged = msg.privileged

        if privileged is not None:
            if privileged:
                self.transfers.add_to_privileged(user)
            else:
                self.transfers.remove_from_privileged(user)

        if status not in (UserStatus.OFFLINE, UserStatus.ONLINE, UserStatus.AWAY):
            log.add_debug("Received an unknown status %(status)s for user %(user)s from the server", {
                "status": status,
                "user": user
            })
            return

        if user in self.watched_users:
            self.user_statuses[user] = status
            self.transfers.get_user_status(msg)

    def connect_to_peer(self, msg):
        """ Server code: 18 """

        if msg.privileged is None:
            return
        if msg.privileged:
            self.transfers.add_to_privileged(msg.user)
        else:
            self.transfers.remove_from_privileged(msg.user)

    def get_user_stats(self, msg):
        """ Server code: 36 """

        user = msg.user
        if user == self.login_username:
            self.transfers.upload_speed = msg.avgspeed

    @staticmethod
    def admin_message(msg):
        """ Server code: 66 """

        log.add_important_info(msg.msg)

    @staticmethod
    def change_password(msg):
        """ Server code: 142 """

        password = msg.password
        config.sections["server"]["passw"] = password
        log.add_important_info("Your password has been changed")
