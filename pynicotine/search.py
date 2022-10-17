# Based on Nicotine+ code, but a slimmed-down and adjusted version of it

# COPYRIGHT (C) 2020-2022 Nicotine+ Contributors
# COPYRIGHT (C) 2016-2018 Mutnick <mutnick@techie.com>
# COPYRIGHT (C) 2016-2017 Michael Labouebe <gfarmerfr@free.fr>
# COPYRIGHT (C) 2008-2011 Quinox <quinox@users.sf.net>
# COPYRIGHT (C) 2006-2009 Daelstorm <daelstorm@gmail.com>
# COPYRIGHT (C) 2003-2004 Hyriand <hyriand@thegraveyard.org>
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

import random

from itertools import islice
from operator import itemgetter

from pynicotine import slskmessages
from pynicotine.logfacility import log
from pynicotine.slskmessages import increment_token
from pynicotine.utils import TRANSLATE_PUNCTUATION


class Search():

    def __init__(self, core, config, queue, share_dbs):
        self.core = core
        self.config = config
        self.queue = queue
        self.searches = {}
        self.token = int(random.random() * (2 ** 31 - 1))
        self.share_dbs = share_dbs

    def request_folder_download(self, user, folder, visible_files):

        # First queue the visible search results
        visible_files.sort(key=itemgetter(1), reverse=self.config.sections["transfers"]["reverseorder"])

        for file in visible_files:
            user, fullpath, destination, size, bitrate, length = file

            self.core.transfers.get_file(
                user, fullpath, destination,
                size=size, bitrate=bitrate, length=length)

        # Ask for the rest of the files in the folder
        self.core.transfers.get_folder(user, folder)

    """ Outgoing search requests """

    @staticmethod
    def add_allowed_token(token):
        """ Allow parsing search result messages for a search ID """
        slskmessages.SEARCH_TOKENS_ALLOWED.add(token)

    @staticmethod
    def remove_allowed_token(token):
        """ Disallow parsing search result messages for a search ID """
        slskmessages.SEARCH_TOKENS_ALLOWED.discard(token)

    def add_search(self, term, ignore):
        self.searches[self.token] = {"id": self.token, "term": term, "mode": "global", "ignore": ignore}
        self.add_allowed_token(self.token)

    def remove_search(self, token):
        self.remove_allowed_token(token)
        search = self.searches.get(token)
        if search is None:
            return
        del self.searches[token]
        self.core.emit('search_remove_search', token)

    def process_search_term(self, search_term):
        # Get excluded words (starting with "-")
        search_term_words = search_term.split()
        search_term_words_special = [p for p in search_term_words if p.startswith(('-', '*')) and len(p) > 1]

        # Remove words starting with "-", results containing these are excluded by us later
        search_term_without_special = ' '.join(p for p in search_term_words if p not in search_term_words_special)

        if self.config.sections["searches"]["remove_special_chars"]:
            """
            Remove special characters from search term
            SoulseekQt doesn't seem to send search results if special characters are included (July 7, 2020)
            """
            stripped_search_term = ' '.join(search_term_without_special.translate(TRANSLATE_PUNCTUATION).split())

            # Only modify search term if string also contains non-special characters
            if stripped_search_term:
                search_term_without_special = stripped_search_term

        # Remove trailing whitespace
        search_term = search_term_without_special.strip()

        # Append excluded words
        for word in search_term_words_special:
            search_term += " " + word

        return search_term, search_term_without_special  #, room, users

    def do_search(self, search_term):

        # Validate search term and run it through plugins
        search_term, _search_term_without_special = self.process_search_term(search_term)

        # Get a new search token
        self.token = increment_token(self.token)

        self.do_global_search(search_term)

        self.add_search(search_term, ignore=False)

        self.core.emit('search_do_search', self.token, search_term)

        return self.token

    def do_global_search(self, text):
        self.queue.append(slskmessages.FileSearch(self.token, text))

    def do_peer_search(self, text, users):
        for user in users:
            self.queue.append(slskmessages.UserSearch(user, self.token, text))

    def file_search_result(self, msg):
        """ Peer message: 9 """

        if msg.token not in slskmessages.SEARCH_TOKENS_ALLOWED:
            return

        search = self.searches.get(msg.token)

        if search is None or search["ignore"]:
            return

        username = msg.init.target_user
        ip_address = msg.init.addr[0]

        if self.core.network_filter.is_user_ignored(username):
            return

        if self.core.network_filter.is_ip_ignored(ip_address):
            return

        self.core.emit('search_show_search_result', msg, username)

    def search_request(self, msg):
        """ Server code: 26, 42 and 120 """

        self.process_search_request(msg.searchterm, msg.user, msg.token, direct=True)

    def distrib_search(self, msg):
        """ Distrib code: 3 """

        self.process_search_request(msg.searchterm, msg.user, msg.token, direct=False)

    """ Incoming search requests """

    @staticmethod
    def update_search_results(results, word_indices, exclude_word=False):
        """ Updates the search result list with indices for a new word """

        if word_indices is None:
            if exclude_word:
                # We don't care if an excluded word doesn't exist in our DB
                return results

            # Included word does not exist in our DB, no results
            return None

        if results is None:
            if exclude_word:
                # No results yet, but word is excluded. Bail.
                return set()

            # First match for included word, return results
            return set(word_indices)

        if exclude_word:
            # Remove results for excluded word
            results.difference_update(word_indices)
        else:
            # Only retain common results for all words so far
            results.intersection_update(word_indices)

        return results

    def create_search_result_list(self, searchterm, wordindex, excluded_words, partial_words):
        """ Returns a list of common file indices for each word in a search term """

        try:
            words = searchterm.split()
            num_words = len(words)
            results = None

            for current_index, word in enumerate(words):
                exclude_word = False

                if word in excluded_words:
                    # Excluded search words (e.g. -hello)

                    if results is None and current_index < num_words:
                        # Re-append the word so we can re-process it once we've found a match
                        words.append(word)
                        continue

                    exclude_word = True

                elif word in partial_words:
                    # Partial search words (e.g. *ello)

                    partial_results = set()

                    for complete_word, indices in wordindex.items():
                        if complete_word.endswith(word):
                            partial_results.update(indices)

                    if partial_results:
                        results = self.update_search_results(results, partial_results)
                        continue

                results = self.update_search_results(results, wordindex.get(word), exclude_word)

                if results is None:
                    # No matches found
                    break

            return results

        except ValueError:
            log.add_debug("Error: DB closed during search, perhaps due to rescanning shares or closing the application")
            return None

    def process_search_request(self, searchterm, user, token, direct=False):
        """ Note: since this section is accessed every time a search request arrives several
            times per second, please keep it as optimized and memory sparse as possible! """

        if not searchterm:
            return

        if not self.config.sections["searches"]["search_results"]:
            # Don't return _any_ results when this option is disabled
            return

        if not direct and user == self.core.login_username:
            # We shouldn't send a search response if we initiated the search request,
            # unless we're specifically searching our own username
            return

        maxresults = self.config.sections["searches"]["maxresults"]

        if maxresults == 0:
            return

        # Remember excluded/partial words for later
        excluded_words = []
        partial_words = []

        if '-' in searchterm or '*' in searchterm:
            for word in searchterm.split():
                if len(word) < 1:
                    continue

                if word.startswith('-'):
                    for subword in word.translate(TRANSLATE_PUNCTUATION).split():
                        excluded_words.append(subword)

                elif word.startswith('*'):
                    for subword in word.translate(TRANSLATE_PUNCTUATION).split():
                        partial_words.append(subword)

        # Strip punctuation
        searchterm_old = searchterm
        searchterm = searchterm.lower().translate(TRANSLATE_PUNCTUATION).strip()

        if len(searchterm) < self.config.sections["searches"]["min_search_chars"]:
            # Don't send search response if search term contains too few characters
            return

        checkuser, _reason = self.core.network_filter.check_user(user, None)

        if not checkuser:
            return

        if checkuser == 2:
            wordindex = self.share_dbs.get("buddywordindex")
        else:
            wordindex = self.share_dbs.get("wordindex")

        if wordindex is None:
            return

        # Find common file matches for each word in search term
        resultlist = self.create_search_result_list(searchterm, wordindex, excluded_words, partial_words)

        if not resultlist:
            return

        if checkuser == 2:
            fileindex = self.share_dbs.get("buddyfileindex")
        else:
            fileindex = self.share_dbs.get("fileindex")

        if fileindex is None:
            return

        fileinfos = []
        numresults = min(len(resultlist), maxresults)

        for index in islice(resultlist, numresults):
            fileinfo = fileindex.get(repr(index))

            if fileinfo is not None:
                fileinfos.append(fileinfo)

        if numresults != len(fileinfos):
            log.add_debug(("Error: File index inconsistency while responding to search request \"%(query)s\". "
                           "Expected %(expected_num)i results, but found %(total_num)i results in database."), {
                "query": searchterm_old,
                "expected_num": numresults,
                "total_num": len(fileinfos)
            })
            numresults = len(fileinfos)

        if not numresults:
            return

        fileinfos.sort(key=itemgetter(1))

        uploadspeed = self.core.transfers.upload_speed
        queuesize = self.core.transfers.get_upload_queue_size()
        slotsavail = self.core.transfers.allow_new_uploads()
        fifoqueue = self.config.sections["transfers"]["fifoqueue"]

        message = slskmessages.FileSearchResult(
            None, self.core.login_username,
            token, fileinfos, slotsavail, uploadspeed, queuesize, fifoqueue)

        self.core.send_message_to_peer(user, message)

        log.add_search("User %(user)s is searching for \"%(query)s\", found %(num)i results", {
            'user': user,
            'query': searchterm_old,
            'num': numresults
        })
