from collections import deque
import os
import json
import re
import sys
import shutil
import threading
import time
import urllib.parse as parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from pynicotine.config import config
from pynicotine.logfacility import log
from pynicotine.pynicotine import NicotineCore

import pymediainfo

_path = os.path.dirname(os.path.realpath(__file__))

# Config
HTTP_HOST = 'localhost'
HTTP_PORT = 8000
HTTP_PUBLIC_DIR = os.path.join(_path, 'public')

SLSK_CONFIG_FILE = os.path.join(_path, 'config.ini')
SLSK_DATA_DIR = os.path.join(_path, 'data')

MAX_SEARCH_SECONDS = 5
MAX_SEARCH_RESULTS = 1000

MAX_DOWNLOAD_SECONDS = 300

# Filter
MIN_SPEED = 512 * 1024

MIN_BITRATE = 128
MAX_BITRATE = 192

# Globals
downloads_dir = os.path.join(HTTP_PUBLIC_DIR, 'downloads')
download_progress = {}
slsk_app = None

########################################
# Utilities
########################################

def foldername (fn):
    parts = re.split('/|\\\\', fn)
    return parts[-2] if len(parts) > 1 else ''

def filename (fn):
    return re.split('/|\\\\', fn)[-1]

def mediainfo (fn):
    return pymediainfo.MediaInfo.parse(fn, cover_data=False).to_data()

def get_albums(results, album_filter=None, artist_filter=None):
    albums = {}
    for song in results:
        parent_folder = foldername(song['file'])
        album = '[' + song['user'] +'] ' + parent_folder
        if not album in albums:
            albums[album] = []
        albums[album].append(song)
    # make sure titles inside albums are sorted
    for k,songs in albums.items():
        songs.sort(key=lambda song: song['file'])
    return albums


########################################
# Simple HTTP request handler
########################################
class MyHTTPRequestHandler(SimpleHTTPRequestHandler):

    def __init__(self, request, client_address, server, directory=None):
        super().__init__(request, client_address, server, directory=HTTP_PUBLIC_DIR)
        self.close_connection = True

    def log_message(self, format, *args):
        pass

    def _serve_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def handle_list(self, params):
        data = {'.':[]}
        files = sorted(os.listdir(downloads_dir))
        for f in files:
            if f.startswith('.'):
                continue
            if os.path.isdir(os.path.join(downloads_dir, f)):
                data[f] = sorted(os.listdir(os.path.join(downloads_dir, f)))
            else:
                data['.'].append(f)
        self._serve_json(data)

    def handle_search(self, params):
        token = slsk_app.search(params['s'][0].lower())

        # wait up to ... sec. for search results
        for i in range(MAX_SEARCH_SECONDS):
            if slsk_app.check_search_finished(token):
                break
            time.sleep(1)

        slsk_app.stop_search(token)

        albums = get_albums(slsk_app.get_and_clear_search_results(token))
        self._serve_json(albums)

    def handle_download(self, params):
        album_dir = os.path.join(downloads_dir, params['album'][0])
        mp3_file = filename(params['file'][0])
        full_path = os.path.join(album_dir, mp3_file)
        mp3_url = parse.quote('/downloads/' + params['album'][0] + '/' + mp3_file)

        if not os.path.isdir(album_dir):
            os.mkdir(album_dir)

        elif os.path.isfile(full_path):
            return self._serve_json({'mp3': mp3_url})

        k = params['user'][0] + ':' + params['file'][0]
        download_progress[k] = 0

        transfer = slsk_app.download_file(params['user'][0], params['file'][0], path=album_dir)

        for i in range(MAX_DOWNLOAD_SECONDS):
            time.sleep(1)
            if transfer:
                if transfer.status == 'Finished':
                    del download_progress[k]
                    self._serve_json({'status': True, 'mp3': mp3_url})
                    return
                elif transfer.size is not None and transfer.last_byte_offset is not None and transfer.size > 0:
                    download_progress[k] = transfer.last_byte_offset / transfer.size

        # download timed out
        self._serve_json({'status': False})

    def handle_mediainfos(self, params):
        try:
            # convert media url to local path
            full_path = os.path.join(HTTP_PUBLIC_DIR, parse.urlparse(params['src'][0]).path[1:])
            self._serve_json({'status': True, 'mediainfos': mediainfo(full_path)})
        except:
            self._serve_json({'status': False})

    def handle_prog(self, params):
        k = params['user'][0] + ':' + params['file'][0]
        self._serve_json({'prog': download_progress[k]} if k in download_progress else {})

    def handle_rename_song(self, params):
        try:
            if params['album'][0] == '.':
                params['album'][0] = ''
            os.rename(
                    os.path.join(downloads_dir, params['album'][0], filename(params['file'][0])),
                    os.path.join(downloads_dir, params['album'][0], filename(params['filenew'][0])))
            self._serve_json({'status': True})
        except:
            self._serve_json({'status': False})

    def handle_delete_song(self, params):
        try:
            if params['album'][0] == '.':
                params['album'][0] = ''
            local_file = os.path.join(downloads_dir, params['album'][0], filename(params['file'][0]))
            os.remove(local_file)
            self._serve_json({'status': True})
        except:
            self._serve_json({'status': False})

    def handle_rename_album(self, params):
        try:
            os.rename(
                    os.path.join(downloads_dir, filename(params['album'][0])),
                    os.path.join(downloads_dir, filename(params['albumnew'][0])))
            self._serve_json({'status': True})
        except:
            self._serve_json({'status': False})

    def handle_delete_album(self, params):
        try:
            shutil.rmtree(os.path.join(downloads_dir, filename(params['album'][0])))
            self._serve_json({'status': True})
        except:
            self._serve_json({'status': False})

    def do_GET(self):
        params = parse.urlparse(self.path)
        handler = 'handle_' + params.path[1:]
        if hasattr(self, handler):
            return getattr(self, handler)(parse.parse_qs(params.query))
        try:
            SimpleHTTPRequestHandler.do_GET(self)
        except:
            pass


########################################
# Simple Soulseek app
########################################
class MySlskApplication():

    def __init__(self):

        self._core = NicotineCore(None, None)
        self._network_msgs = deque()

        sys.excepthook = self._on_critical_error
        threading.excepthook = self._on_critical_error_threading

        config.load_config(SLSK_CONFIG_FILE, SLSK_DATA_DIR)

        log.log_levels = set(["download", "upload"] + config.sections["logging"]["debugmodes"])

        self._search_results = {}  # token => list of files
        self._search_finished = {}  # token => boolean

        self._core.on('search_do_search', self._on_do_search)
        self._core.on('search_show_search_result', self._on_show_search_result)

    def _on_critical_error(self, _exc_type, exc_value, _exc_traceback):
        self._core.quit()
        raise exc_value

    @staticmethod
    def _on_critical_error_threading(args):
        raise args.exc_value

    def _on_new_messages(self, msgs):
        self._network_msgs.extend(msgs)

    def _on_do_search(self, token, search_term):
        self._search_results[token] = []
        self._search_finished[token] = False

    # Receives search results and saves them in list
    def _on_show_search_result(self, msg, username):
        # Filter: ignore users with low speed or without free slots
        if self._search_finished[msg.token] or not msg.freeulslots or msg.ulspeed < MIN_SPEED:
            return
        for song in msg.list:

            # Filter for browser compatible files: mp3 only (also allow .ogg and .aac?)
            if not song[1].lower().endswith('.mp3'):
                continue

            # Filter by bitrate
            if '0' in song[4] and (song[4]['0'] < MIN_BITRATE or song[4]['0'] > MAX_BITRATE):
                continue

            self._search_results[msg.token].append( {'user': username, 'file': song[1]} )
            if len(self._search_results[msg.token]) >= MAX_SEARCH_RESULTS:
                # Todo: prevent truncated album by removing the last album?
                self._search_finished[msg.token] = True
                break

    ### public ###

    def search(self, search_term):
        return self._core.search.do_search(search_term)

    def stop_search(self, token):
        self._core.search.remove_search(token)
        self._search_finished[token] = True  # force

    def check_search_finished(self, token):
        return self._search_finished[token]

    def get_and_clear_search_results(self, token):
        results = list(self._search_results[token])
        del self._search_results[token]
        del self._search_finished[token]
        return results

    def download_file(self, user, filename, path=""):
        return self._core.transfers.get_file(user, filename, path)

    def run(self):
        self._core.start(self._on_new_messages)

        if not self._core.connect():
            # Network error, exit code 1
            sys.exit(1)

        # Main loop, process messages from networking thread
        while not self._core.shutdown:
            if self._network_msgs:
                msgs = []
                while self._network_msgs:
                    msgs.append(self._network_msgs.popleft())
                self._core.network_event(msgs)
            time.sleep(1 / 60)

        # Shut down with exit code 0 (success)
        return 0

    def quit(self):
        self._core.quit()


if __name__ == '__main__':
    slsk_app = MySlskApplication()

    MyHTTPRequestHandler.extensions_map['.js'] = 'application/javascript'
    httpd = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), MyHTTPRequestHandler)
    log.add("Serving HTTP at port: %i", HTTP_PORT)

    slsk_thread = threading.Thread(target=slsk_app.run)
    slsk_thread.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.add('Ctrl-C received, shutting down HTTP server')

    httpd.server_close()
    log.add('HTTP Server stopped.')

    # Signal termination
    slsk_app.quit()

    # Wait for actual termination
    slsk_thread.join()

