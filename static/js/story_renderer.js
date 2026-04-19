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
    
    // Initialize Path Layer
    if (window.storyPath) window.storyPath.remove();
    window.storyPath = L.polyline([], {
        color: 'var(--accent-gold)',
        weight: 3,
        opacity: 0.6,
        dashArray: '5, 10',
        lineCap: 'round',
        lineJoin: 'round'
    }).addTo(map);

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

    // Helper to calculate coordinate distance (rough approximation for thresholding)
    function getCoordDistance(p1, p2) {
        return Math.sqrt(Math.pow(p2.lat - p1.lat, 2) + Math.pow(p2.lon - p1.lon, 2));
    }

    // Helper for gliding animations across a static overview
    async function glideMarkerAcrossOverview(marker, s1, s2, durationPerSegment = 45) {
        const dist = getCoordDistance(s1, s2);
        const threshold = 0.005; // ~500m threshold for "local" jumps
        
        if (dist < 0.0001) {
            // Effectively same point: skip animation
            marker.setLatLng([s2.lat, s2.lon]);
            if (window.storyPath) window.storyPath.addLatLng([s2.lat, s2.lon]);
            return;
        }

        if (dist < threshold) {
            // Local jump: glide without zooming out
            const steps = 15;
            for (let i = 0; i <= steps; i++) {
                if (!window.isStoryPlaying) return;
                const progress = i / steps;
                const lat = s1.lat + (s2.lat - s1.lat) * progress;
                const lon = s1.lon + (s2.lon - s1.lon) * progress;
                marker.setLatLng([lat, lon]);
                if (window.storyPath) window.storyPath.addLatLng([lat, lon]);
                await new Promise(r => setTimeout(r, 20));
            }
            return;
        }

        // 1. Prepare Overview: Fit bounds of Start and End
        map.fitBounds([
            [s1.lat, s1.lon],
            [s2.lat, s2.lon]
        ], { 
            padding: [80, 80], 
            animate: true, 
            duration: 1.0 
        });
        
        // 2. Wait for map tiles to load (Overview state)
        await new Promise(r => setTimeout(r, 1200));

        // 3. Glide Marker (Map remains static)
        const steps = Math.max(30, Math.min(300, Math.floor(dist * 150)));
        for (let i = 0; i <= steps; i++) {
            if (!window.isStoryPlaying) return;
            const progress = i / steps;
            const lat = s1.lat + (s2.lat - s1.lat) * progress;
            const lon = s1.lon + (s2.lon - s1.lon) * progress;
            marker.setLatLng([lat, lon]);
            
            // Add to path every few steps for performance
            if (window.storyPath && i % 2 === 0) window.storyPath.addLatLng([lat, lon]);
            
            await new Promise(r => setTimeout(r, durationPerSegment));
        }
        if (window.storyPath) window.storyPath.addLatLng([s2.lat, s2.lon]);

        // 4. Arrive: Zoom in to Destination
        map.setView([s2.lat, s2.lon], 14, { animate: true, duration: 1.0 });
        await new Promise(r => setTimeout(r, 1000));
    }

    // --- The Animation Loop ---
    let currentIndex = 0;

    async function playNextWaypoint() {
        if (!window.isStoryPlaying || currentIndex >= stations.length) {
            window.stopStoryMode();
            return;
        }

        // UI Sync
        const btnStart = document.getElementById('btn-start-story');
        const btnStop = document.getElementById('btn-stop-story');
        if (btnStart) btnStart.classList.add('d-none');
        if (btnStop) btnStop.classList.remove('d-none');
        if (btnStop) btnStop.classList.add('d-flex');

        const s = stations[currentIndex];
        const nextS = stations[currentIndex + 1];
        
        // 1. Initial Position (Zoomed in)
        if (currentIndex === 0) {
            map.setView([s.lat, s.lon], 14);
            storyMarker.setLatLng([s.lat, s.lon]);
        }
        
        // Force unified Albatross/Seagull Icon
        const displayIcon = '🕊️'; 
        
        storyMarker.setIcon(L.divIcon({
            html: `<div class="story-marker-icon bird-flying">${displayIcon}</div>`,
            className: 'story-marker-container',
            iconSize: [45, 45]
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

        // 5. Glide to next waypoint
        if (nextS) {
            await glideMarkerAcrossOverview(storyMarker, s, nextS, 45);
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
    if (window.storyPath) {
        window.storyPath.remove();
        window.storyPath = null;
    }
    const overlay = document.getElementById('story-overlay');
    if (overlay) overlay.remove();
    
    // UI RESTORE
    const btnStart = document.getElementById('btn-start-story');
    const btnStop = document.getElementById('btn-stop-story');
    if (btnStart) btnStart.classList.remove('d-none');
    if (btnStop) {
        btnStop.classList.add('d-none');
        btnStop.classList.remove('d-flex');
    }

    showToast("🎬 Story beendet.");
};
