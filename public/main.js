const PROGRESS_QUERY_PERIOD_MS = 1000;
const MAX_DOWNLOAD_SECONDS = 300;

const div_result_collection = document.querySelector('#result-collection');
const div_result_search = document.querySelector('#result-search');
const div_playlist = document.querySelector('#playlist');
const div_result_mediainfos = document.querySelector('#mediainfos');

const input_search = document.querySelector('#input-search');
const player = document.querySelector('#player');
const div_now_playing = document.querySelector('#now-playing');

const btn_collection = document.querySelector('input#btn-collection');
const btn_mediainfos = document.querySelector('input#btn-mediainfos');

let collection = {};

function timeout(sec)
{
	let controller = new AbortController();
	setTimeout(() => controller.abort(), sec * 1000);
	return controller;
}

function show_current_song(track, album)
{
	btn_mediainfos.disabled = false;
	div_now_playing.innerHTML = (!album || album == '.' ? '' : album + ' - ') + track;
}

function show_mediainfos(infos)
{
    if (infos && infos.tracks)
    {
        let output = '';
        for (let t of infos.tracks)
        {
        	delete t['count'];
        	delete t['count_of_stream_of_this_kind'];
        	delete t['kind_of_stream'];
        	delete t['stream_identifier'];
			delete t['proportion_of_this_stream'];

			delete t['complete_name'];
			delete t['folder_name'];
			delete t['file_name_extension'];
			delete t['format_extensions_usually_used'];

			delete t['file_creation_date'];
			delete t['file_creation_date__local'];
			delete t['file_last_modification_date'];
			delete t['file_last_modification_date__local'];

			const prop_esc = t['track_type'];
			delete t['track_type'];
			output += `<li><span class="prop">${prop_esc}</span> <span class="collapser"></span><ul class="array collapsible">`;

			for (let k in t)
			{
            	if (k.startsWith('other_'))
            		continue;
            	output += `<li><b>${jsString(k)}:</b> <span title="${jsString(t[k])}">${jsString(t[k])}</span></li>`;
			}
			output += `</ul></li>`;
	    	div_result_mediainfos.innerHTML = `<div class="tree"><ul class="obj collapsible">${output}</ul></div>`;
			div_result_mediainfos.scrollTop = 0;
        }
    }
}

function play(el)
{
	show_current_song(el.dataset.file, el.dataset.album);
    player.src = `/downloads/${encodeURIComponent(el.dataset.album)}/${encodeURIComponent(el.dataset.file)}`;
    player.play();
    return false;
}

function load(el)
{
    const span_status = el.querySelector('span');
    span_status.style.display = 'inline-block';
    let finished = false;

    let interval_id = setInterval(function(){
        fetch(`/prog?user=${encodeURIComponent(el.dataset.user)}&file=${encodeURIComponent(el.dataset.file)}`)
        .then(res => res.json())
        .then(res =>
        {
            if (!finished && res.prog)
            {
                span_status.style.boxShadow = `inset ${Math.round(res.prog * 100)}px 0 0 0 lightblue`;
            }
        })
	    .catch(err => {});
    }, PROGRESS_QUERY_PERIOD_MS);

    fetch(`/download?album=${encodeURIComponent(el.dataset.album)}&user=${encodeURIComponent(el.dataset.user)}&file=${encodeURIComponent(el.dataset.file)}`, {
    	signal: timeout(MAX_DOWNLOAD_SECONDS).signal
    })
    .then(res => res.json())
    .then(res => {
        finished = true;
        clearInterval(interval_id);
        if (res.mp3)
        {
            span_status.style.boxShadow = `inset 100px 0 0 0 greenyellow`;

            // make playable on click, remove context menu
            el.dataset.file = get_song_name(el.dataset.file);
            el.onclick = function(){return play(el)};
            el.classList.remove('cm');
        }
    })
    .catch(err =>
    {
        clearInterval(interval_id);
        span_status.style.boxShadow = `inset 100px 0 0 0 lightpink`;
        //console.log('Download failed', err);
    });

    return false;
}

function get_song_name (fn)
{
    let backSlashIndex = 0;
    for (let i = fn.length - 1; i > 0; i--)
    {
        if (fn[i] === `\\`[0])
        {
            backSlashIndex = i;
            break;
        };
    }
    return fn.slice(backSlashIndex + 1);
}

const html_map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
};

function htmlEncode(t) {
    return t.replace(/[&<>"']/g, (m) => html_map[m]);
}

// remove quotes and encodes
function jsString(s) {
	return htmlEncode(JSON.stringify(s).slice(1, -1));
}

function search()
{
    div_result_search.innerHTML = '';
    fetch(`/search?s=${encodeURIComponent(input_search.value)}`)
    .then(res => res.json())
    .then(json =>
    {
    	let output = '';
    	for (const prop in json)
    	{
    	    const prop_esc = jsString(prop);
    		output += `<li><span class="prop cm" data-cm="cm-album-search">${prop_esc}</span> <span class="collapser collapsed"></span><ul class="array collapsible collapsed">`;
        	for (let i = 0; i < json[prop].length; i++)
        	{
        		let mp3 = get_song_name(json[prop][i].file);
        		let file_exists = collection[prop] && collection[prop].includes(mp3);

        	    file = htmlEncode(json[prop][i].file);
        	    if (file_exists)
        			output += `<li><a class="cm" data-cm="cm-song-collection" href="#" title="${file}" data-album="${prop_esc}" data-user="${htmlEncode(json[prop][i].user)}" data-file="${mp3}" onclick="return play(this)">${jsString(mp3)}<span class="finished"></span></a></li>`;
        	    else
        			output += `<li><a class="cm" data-cm="cm-song-search" href="#" title="${file}" data-album="${prop_esc}" data-user="${htmlEncode(json[prop][i].user)}" data-file="${file}" onclick="return load(this)">${jsString(mp3)}<span></span></a></li>`;
        	}
    		output += `</ul></li>`;
    	}
    	div_result_search.innerHTML = `<div class="tree"><ul class="obj collapsible">${output}</ul></div>`;
		div_result_search.scrollTop = 0;
    })
    .catch(err =>
    {
	});
}

input_search.onkeyup = function(e)
{
    if (e.keyCode == 13)
        search();
};

function show_collection()
{
    fetch('/list')
    .then(res => res.json())
    .then(json =>
    {
    	collection = json;

    	// save non-collapsed nodes
    	let non_collapsed_folders = [];
    	for (let el of div_result_collection.querySelectorAll('.collapser:not(.collapsed)'))
    		non_collapsed_folders.push(el.parentNode.children[0].innerText);

    	let output = '';
    	for (const prop in json)
    	{
    	    if (prop == '.')
    	        continue;
    	    let collapsed = non_collapsed_folders.includes(jsString(prop)) ? '' : ' collapsed';
    		output += `<li><span class="prop cm" data-cm="cm-album-collection">${jsString(prop)}</span> <span class="collapser${collapsed}"></span><ul class="array collapsible${collapsed}">`;
        	for (let i = 0; i < json[prop].length; i++)
        	{
        	    file = htmlEncode(json[prop][i]);
        		output += `<li><a class="cm" data-cm="cm-song-collection" href="#" title="${file}" data-album="${jsString(prop)}" data-file="${file}" onclick="return play(this)">${file}</a></li>`;
        	}
    		output += '</ul></li>';
    	}
        for (let file of json['.'])
        {
            file = htmlEncode(file);
            output += `<li><a class="cm" data-cm="cm-song-collection" href="#" title="${file}" data-album="." data-file="${file}" onclick="return play(this)">${file}</a></li>`;
        }

		div_result_collection.innerHTML = `<div class="tree"><ul class="obj collapsible">${output}</ul></div>`;
    	div_result_collection.scrollTop = 0;
    });
}

btn_collection.onclick = show_collection;
btn_collection.click();

function get_mediainfos()
{
	div_result_mediainfos.innerHTML = '';
    fetch(`/mediainfos?src=${player.src}`)
    .then(res => res.json())
    .then(json =>
    {
    	show_mediainfos(json.mediainfos)
    })
    .catch(err => {});
}

btn_mediainfos.onclick = get_mediainfos;


let cm, cm_target;

const scope = document.querySelector("body");

scope.addEventListener("contextmenu", (e) =>
{
    if (cm)
    {
        cm.classList.remove("visible");
        cm = null;
    }
    if (e.target.classList.contains('cm'))
    {
        e.preventDefault();
        const { clientX: mouseX, clientY: mouseY } = e;

        cm_target = e.target;
        cm = document.getElementById(cm_target.dataset.cm);
        cm.style.top = `${mouseY}px`;
        cm.style.left = `${mouseX}px`;
        cm.classList.add("visible");
    }
});

scope.addEventListener("click", (e) =>
{
    if (cm)
    {
        cm.classList.remove("visible");
        cm = null;
    }
});

function onContextMenuItemClicked()
{
    switch (cm_target.dataset.cm)
    {
        case 'cm-song-collection':
            switch (this.innerText)
            {
                case 'Play file':
                    cm_target.click();
                    break;

                case 'Add to Playlist':
                    playlist_append(cm_target.dataset);
                    break;

                case 'Rename file':
                    const filenew = prompt('Enter new filename:', cm_target.dataset.file);
                    if (!filenew || filenew == cm_target.dataset.file)
                        return;
                    fetch(`/rename_song?album=${encodeURIComponent(cm_target.dataset.album)}&file=${encodeURIComponent(cm_target.dataset.file)}&filenew=${encodeURIComponent(filenew)}`)
                    .then(res => res.json())
                    .then(json => {
                        show_collection();
                    });
                    break;

                case 'Delete file':
                    if (!confirm(`Really delete file '${cm_target.dataset.file}'?`))
                        return;
                    fetch(`/delete_song?album=${encodeURIComponent(cm_target.dataset.album)}&file=${encodeURIComponent(cm_target.dataset.file)}`)
                    .then(res => res.json())
                    .then(json => {
                        show_collection();
                    });
                    break;
            }
            break;

        case 'cm-album-collection':
            switch (this.innerText)
            {
                case 'Add to Playlist':
                    for (let li of cm_target.parentNode.children[2].children)
                    	playlist_append(li.children[0].dataset);
                    break;

                case 'Rename folder':
                    const albumnew = prompt('Enter new folder name:', cm_target.innerText);
                    if (!albumnew || albumnew == cm_target.innerText)
                        return;
                    fetch(`/rename_album?album=${encodeURIComponent(cm_target.innerText)}&albumnew=${encodeURIComponent(albumnew)}`)
                    .then(res => res.json())
                    .then(json => {
                        show_collection();
                    });
                    break;
                case 'Delete folder':
                    if (!confirm(`Really delete complete folder '${cm_target.innerText}'?`))
                        return;
                    fetch(`/delete_album?album=${encodeURIComponent(cm_target.innerText)}`)
                    .then(res => res.json())
                    .then(json => {
                        show_collection();
                    });
                    break;
            }
            break;

        case 'cm-song-search':
            switch (this.innerText)
            {
                case 'Download song':
                    cm_target.click();
                    break;
//                case 'Download and play':
//                    //cm_target.click();
//                    break;
            }
            break;

        case 'cm-album-search':
            switch (this.innerText)
            {
                case 'Download album':
                    for (let li of cm_target.parentNode.children[2].children)
                    	li.children[0].click();
                    break;
            }
            break;

        case 'cm-playlist':
            switch (this.innerText)
            {
                case 'Clear Playlist':
					playlist_clear();
                    break;
            }
            break;

        case 'cm-playlist-item':
			const row = cm_target.parentNode.parentNode;
			const idx = Array.prototype.indexOf.call(row.parentNode.childNodes, row);
            switch (this.innerText)
            {
                case 'Move Up':
                	playlist_move_up(idx);
                	break;
                case 'Move Down':
                	playlist_move_down(idx);
                	break;
                case 'Remove Item':
					playlist_remove_by_index(idx);
                    break;
            }
            break;

    }
}

for (let el of document.querySelectorAll('.context-menu .item'))
    el.onclick = onContextMenuItemClicked;

// Add event handler that allows for collapsing and expanding nodes with the mouse
document.addEventListener('click', function(evt)
{
	let collapser = evt.target;
	while (collapser && (!collapser.classList || !collapser.classList.contains('collapser')))
	{
		collapser = collapser.nextSibling;
	}
	if (!collapser || !collapser.classList || !collapser.classList.contains('collapser'))
	{
		return;
	}
	evt.stopPropagation();
	collapser.classList.toggle('collapsed');
	let collapsible = collapser;
	while (collapsible && (!collapsible.classList || !collapsible.classList.contains('collapsible')))
	{
		collapsible = collapsible.nextSibling;
	}
	collapsible.classList.toggle('collapsed');
}, false);

document.addEventListener('keydown', function(evt)
{
	if (evt.ctrlKey && evt.keyCode == 32)
	{
		evt.stopPropagation();
		let first_collapser = document.querySelector('.collapser');
		if (!first_collapser) return;
		let flag = !first_collapser.classList.contains('collapsed');
		for (let el of document.querySelectorAll('.collapser'))
		{
			el.classList.toggle('collapsed', flag);
			el.nextSibling.classList.toggle('collapsed', flag);
		}
	}
}, false);
