"use strict";

let _current_row = null;

// Initializes the html5 audio player and the playlist.
function player_init()
{
	// Handle audio track has ended.
	player.addEventListener('ended', function(e)
	{
		if (_current_row)
			_track_ended();
	}, false);

	player.addEventListener('play', function(e)
	{
		if (_current_row)
			_ui_update_play_button(true);
	}, false);

	player.addEventListener('pause', function(e)
	{
		if (_current_row)
			_ui_update_play_button(false);
	}, false);
}

// Controls playback of the audio element.
function _toggle_play()
{
	if (player.paused)
	{
		player.play();
		_ui_update_play_button(true);
	}
	else
	{
		player.pause();
		_ui_update_play_button(false);
	}
}

// Sets the track if it hasn't already been loaded yet.
function _set_track()
{
	player.src = _current_row.dataset.src;
	show_current_song(_current_row.children[1].outerText);
	_ui_update_active_row();
	player.play();
	//_ui_update_play_button(true); // done by event
}

// Plays the next track when a track has ended playing.
function _track_ended()
{
	const idx = Array.prototype.indexOf.call(div_playlist.children, _current_row);
	_current_row = div_playlist.children[idx < div_playlist.children.length - 1 ? idx + 1 : 0];

	_ui_reset_play_buttons();
	_set_track();
}

// Sets the activly playing item within the playlist.
function _ui_update_active_row()
{
	for (let row of div_playlist.children)
		row.children[1].className = row == _current_row ? 'track-title active-track' : 'track-title';
}

// Updates small toggle button accordingly.
function _ui_update_play_button (audioPlaying)
{
	_current_row.children[0].classList.toggle('playing', audioPlaying);
}

// Resets all toggle buttons to be play buttons.
function _ui_reset_play_buttons()
{
	for (const el of div_playlist.querySelectorAll('.small-toggle-btn'))
		el.classList.toggle('playing', false);
}

function play_row(row)
{
	if (row == _current_row)
		return _toggle_play();

	_ui_reset_play_buttons();
	_current_row = row;
	_set_track();
}

function playlist_clear(s)
{
	div_playlist.innerHTML = '';
}

function playlist_remove_by_index(idx)
{
	div_playlist.children[idx].remove();
}

function _make_row(s)
{
	return `<div class="playlist-row" data-src="/downloads/${encodeURIComponent(s.album)}/${encodeURIComponent(s.file)}" title="${s.album != '.' ? s.album + ' - ' : ''}${s.file}">
		<div class="small-toggle-btn" onclick="play_row(this.parentNode)"></div>
		<div class="track-title" ><a class="playlist-track cm" data-cm="cm-playlist-item" onclick="play_row(this.parentNode.parentNode)" href="#">${s.album != '.' ? s.album + ' - ' : ''}${s.file}</a></div>
	</div>`;
}

function playlist_append(s)
{
	div_playlist.insertAdjacentHTML('beforeend', _make_row(s));
}

function playlist_move_down(idx)
{
	if (idx >= div_playlist.children.length - 1)
		return;
	const row = div_playlist.children[idx];
	row.remove();
	div_playlist.children[idx].after(row);
}

function playlist_move_up(idx)
{
	if (idx == 0)
		return;
	const row = div_playlist.children[idx];
	row.remove();
	div_playlist.children[idx - 1].before(row);
}

player_init();
