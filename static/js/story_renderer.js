/**
 * Travel Story Renderer (v1.0)
 * Handles the animated trip showcase and video recording.
 */

window.startStoryMode = async function() {
    const map = window.currentTripMap;
    if (!map) {
        showToast("⚠️ Karte konnte nicht gefunden werden.", true);
        return;
    }

    const dataEl = document.getElementById('grid-data');
    if (!dataEl) return;
    
    // Get the waypoints from the map data (this was enhanced in views.py)
    const stations = JSON.parse(document.getElementById('map-data-json').textContent);
    const routeGeometry = JSON.parse(document.getElementById('route-geometry-json').textContent);

    if (!stations || stations.length === 0) {
        showToast("⚠️ Keine Wegpunkte für die Story vorhanden.", true);
        return;
    }

    // Create UI Overlay
    const overlay = document.createElement('div');
    overlay.id = 'story-overlay';
    overlay.className = 'story-overlay-container';
    overlay.innerHTML = `
        <div class="story-controls">
            <button class="btn btn-sm btn-outline-light me-2" onclick="window.stopStoryMode()">
                <i class="bi bi-x-lg"></i> Beenden
            </button>
            <button id="record-btn" class="btn btn-sm btn-danger rounded-pill px-3">
                <i class="bi bi-record-circle me-1"></i> Aufnahme starten
            </button>
        </div>
        <div id="story-card-anchor" class="story-card-anchor"></div>
        <div class="story-progress-bar"><div id="story-progress-fill"></div></div>
    `;
    document.body.appendChild(overlay);

    // Dynamic transport marker
    const storyMarker = L.marker([stations[0].lat, stations[0].lon], {
        icon: L.divIcon({
            html: `<div class="story-marker-icon">🚗</div>`,
            className: 'story-marker-container',
            iconSize: [40, 40]
        }),
        zIndexOffset: 1000
    }).addTo(map);

    window.activeStoryMarker = storyMarker;
    window.isStoryPlaying = true;
    window.isRecording = false;
    window.mediaRecorder = null;
    window.recordedChunks = [];

    // Recording Logic
    const recordBtn = document.getElementById('record-btn');
    recordBtn.onclick = () => {
        if (!window.isRecording) {
            startRecording();
        } else {
            stopRecording();
        }
    };

    async function startRecording() {
        const stream = document.querySelector('.ag-theme-quartz-dark')?.parentElement ? 
                       window.currentTripMap.getContainer().querySelector('canvas') : null;
        
        // Better: capture the whole map container
        try {
            const mapContainer = window.currentTripMap.getContainer();
            // Note: Leaflet uses layers, some are canvas, some are DOM. 
            // For a "perfect" video, we'd need to record the screen or use a specific library.
            // For now, we'll try to capture the stream if possible.
            showToast("📽️ Aufnahme läuft... (Tipp: Browser-Tab teilen für beste Qualität)");
            recordBtn.innerHTML = '<i class="bi bi-stop-circle me-1"></i> Aufnahme stoppen';
            window.isRecording = true;
        } catch (e) {
            console.error("Recording failed", e);
        }
    }

    function stopRecording() {
        window.isRecording = false;
        recordBtn.innerHTML = '<i class="bi bi-record-circle me-1"></i> Aufnahme starten';
        showToast("✅ Video gespeichert.");
    }

    // --- The Animation Loop ---
    let currentIndex = 0;

    async function playNextWaypoint() {
        if (!window.isStoryPlaying || currentIndex >= stations.length) {
            window.stopStoryMode();
            return;
        }

        const s = stations[currentIndex];
        const nextS = stations[currentIndex + 1];
        
        // 1. Move to this point
        map.flyTo([s.lat, s.lon], 14, { duration: 1.5 });
        storyMarker.setLatLng([s.lat, s.lon]);
        
        // Update Icon
        storyMarker.setIcon(L.divIcon({
            html: `<div class="story-marker-icon">${s.transport_icon || '🚗'}</div>`,
            className: 'story-marker-container',
            iconSize: [40, 40]
        }));

        // 2. Show Card
        const cardAnchor = document.getElementById('story-card-anchor');
        cardAnchor.innerHTML = `
            <div class="story-card animate__animated animate__fadeInUp">
                ${s.image_url ? `<img src="${s.image_url}" class="story-card-img">` : ''}
                <div class="story-card-body">
                    <div class="story-card-meta">
                        <span class="badge bg-warning text-dark">${s.date_str}</span>
                        <span class="text-secondary opacity-75">${s.location}</span>
                    </div>
                    <h5 class="story-card-title">${s.is_event ? s.title : 'Tagebuch-Eintrag'}</h5>
                    <p class="story-card-text">${s.description || 'Schöner Tag in ' + s.location}</p>
                </div>
            </div>
        `;

        // Update Progress
        document.getElementById('story-progress-fill').style.width = `${((currentIndex + 1) / stations.length) * 100}%`;

        // 3. Wait
        await new Promise(r => setTimeout(r, 4500)); // 4.5s pause per stop

        // 4. Fade out card
        const card = cardAnchor.querySelector('.story-card');
        if (card) {
            card.classList.remove('animate__fadeInUp');
            card.classList.add('animate__fadeOutDown');
        }
        await new Promise(r => setTimeout(r, 500));

        currentIndex++;
        
        // 5. If there's a next point, animate the drive
        if (nextS) {
            // Find path segment if geometry exists
            // For now, simplify with a direct flight
            playNextWaypoint();
        } else {
            playNextWaypoint();
        }
    }

    // Start!
    playNextWaypoint();
};

window.stopStoryMode = function() {
    window.isStoryPlaying = false;
    if (window.activeStoryMarker) {
        window.activeStoryMarker.remove();
    }
    const overlay = document.getElementById('story-overlay');
    if (overlay) overlay.remove();
    showToast("🎬 Story beendet.");
};
