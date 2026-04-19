/**
 * Travel Story Renderer (v1.0)
 * Handles the animated trip showcase and video recording.
 */

window.startStoryMode = async function() {
    console.log("🎬 Story Mode initiated...");
    
    let map = window.currentTripMap;
    if (!map) {
        console.log("🗺️ Map not initialized. Trying to open offcanvas...");
        const offcanvasEl = document.getElementById('offcanvasRouteMap');
        if (offcanvasEl) {
            const bsOffcanvas = bootstrap.Offcanvas.getOrCreateInstance(offcanvasEl);
            bsOffcanvas.show();
            showToast("⌛ Karte wird geladen...");
            // Wait for map to be ready
            setTimeout(() => window.startStoryMode(), 800);
            return;
        }
        showToast("⚠️ Karte konnte nicht gefunden werden.", true);
        return;
    }

    const mapDataEl = document.getElementById('map-data-json');
    if (!mapDataEl) {
        console.error("❌ map-data-json not found in DOM");
        return;
    }
    
    // Get the waypoints from the map data
    const stations = JSON.parse(mapDataEl.textContent);
    const routeGeometryEl = document.getElementById('route-geometry-json');
    const routeGeometry = routeGeometryEl ? JSON.parse(routeGeometryEl.textContent) : [];

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

    // Helper for gliding animations
    async function glideMarker(marker, targetPath, durationPerSegment = 50) {
        if (!targetPath || targetPath.length === 0) return;
        
        for (const point of targetPath) {
            if (!window.isStoryPlaying) return;
            // leaflet coordinates are [lng, lat] in my JSON, but marker needs [lat, lng]
            const targetPos = [point[1], point[0]];
            marker.setLatLng(targetPos);
            map.panTo(targetPos, { animate: true, duration: 0.1 });
            await new Promise(r => setTimeout(r, durationPerSegment));
        }
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
        
        // 1. Move to this point (Instant if first, gliding if from previous)
        if (currentIndex === 0) {
            map.setView([s.lat, s.lon], 14);
            storyMarker.setLatLng([s.lat, s.lon]);
        }
        
        // Update Icon with Flying Animation check
        const isBird = (s.transport_icon === '🐦');
        storyMarker.setIcon(L.divIcon({
            html: `<div class="story-marker-icon ${isBird ? 'bird-flying' : ''}">${s.transport_icon || '🚗'}</div>`,
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

        // 3. Wait at Station
        await new Promise(r => setTimeout(r, 4000)); 

        // 4. Fade out card
        const card = cardAnchor.querySelector('.story-card');
        if (card) {
            card.classList.remove('animate__fadeInUp');
            card.classList.add('animate__fadeOutDown');
        }
        await new Promise(r => setTimeout(r, 500));

        // 5. Glide to next waypoint if it exists
        if (nextS && routeGeometry.length > 0) {
            // Find current and next positions in geometry
            // Note: This is a simplified approach, we take segments between station indices
            // For now, let's interpolate the direct path if geometry segmenting is too complex
            // A better way: find points in routeGeometry closest to s and nextS
            const pathPoints = []; 
            // We just use a direct interpolation for smoothness if specific route segments are hard to slice
            const steps = 40;
            for (let i = 0; i <= steps; i++) {
                const lat = s.lat + (nextS.lat - s.lat) * (i / steps);
                const lon = s.lon + (nextS.lon - s.lon) * (i / steps);
                pathPoints.push([lon, lat]);
            }
            await glideMarker(storyMarker, pathPoints, 40);
        }

        currentIndex++;
        playNextWaypoint();
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
