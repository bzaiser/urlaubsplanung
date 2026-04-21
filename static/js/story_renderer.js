/**
 * Travel Story Renderer (v1.1)
 * Handles the animated trip showcase following the actual route path.
 */

window.startStoryMode = async function() {
    console.log("🎬 Story Mode initiated...");
    
    let map = window.currentTripMap;
    if (!map) {
        const offcanvasEl = document.getElementById('offcanvasRouteMap');
        if (offcanvasEl) {
            const bsOffcanvas = bootstrap.Offcanvas.getOrCreateInstance(offcanvasEl);
            bsOffcanvas.show();
            setTimeout(() => window.startStoryMode(), 800);
            return;
        }
        return;
    }

    const mapDataEl = document.getElementById('map-data-json');
    const stations = mapDataEl ? JSON.parse(mapDataEl.textContent) : [];
    const routeGeometryEl = document.getElementById('route-geometry-json');
    const routeGeometry = routeGeometryEl ? JSON.parse(routeGeometryEl.textContent) : [];

    if (!stations || stations.length === 0) return;

    // --- CONFIGURATION ---
    const ICON_DEFAULT = '🕊️'; // Bird. Change to '🚐', '🚗' etc. as needed.
    const SPEED_FACTOR = 1.5; // Multiplier for faster flight
    const WAIT_STATION = 2500; // Time spent at each card
    
    // UI Setup: Switch to Story Header
    const btnStart = document.getElementById('btn-start-story');
    const btnActive = document.getElementById('story-active-controls');
    if (btnStart) btnStart.classList.add('d-none');
    if (btnActive) {
        btnActive.classList.remove('d-none');
        btnActive.classList.add('d-flex');
    }

    // Progress Overlay (Minimal)
    const overlay = document.createElement('div');
    overlay.id = 'story-overlay';
    overlay.className = 'story-overlay-container';
    overlay.innerHTML = `
        <div id="story-card-anchor" class="story-card-anchor"></div>
        <div class="story-progress-bar"><div id="story-progress-fill"></div></div>
    `;
    document.body.appendChild(overlay);

    // Dynamic transport marker
    const storyMarker = L.marker([stations[0].lat, stations[0].lon], {
        icon: L.divIcon({
            html: `<div class="story-marker-icon bird-flying">${ICON_DEFAULT}</div>`,
            className: 'story-marker-container',
            iconSize: [45, 45]
        }),
        zIndexOffset: 1000
    }).addTo(map);

    window.activeStoryMarker = storyMarker;
    window.isStoryPlaying = true;
    
    // Path Management
    if (window.storyPath) window.storyPath.remove();
    window.storyPath = L.polyline([], {
        color: 'var(--accent-gold)', weight: 3, opacity: 0.6, dashArray: '5, 10'
    }).addTo(map);

    // Recording Logic
    const recordBtn = document.getElementById('btn-record-story');
    if (recordBtn) {
        recordBtn.onclick = () => {
            if (!window.isRecording) {
                window.isRecording = true;
                recordBtn.classList.replace('btn-outline-danger', 'btn-danger');
                recordBtn.innerHTML = '<i class="bi bi-stop-circle-fill"></i><span class="small fw-bold text-uppercase d-none d-md-inline">Stop Rec</span>';
                showToast("📽️ Aufnahme gestartet (Browser-Tab teilen empfohlen)");
            } else {
                window.isRecording = false;
                recordBtn.classList.replace('btn-danger', 'btn-outline-danger');
                recordBtn.innerHTML = '<i class="bi bi-record-circle-fill"></i><span class="small fw-bold text-uppercase d-none d-md-inline">Rec</span>';
                showToast("✅ Video gespeichert.");
            }
        };
    }

    // --- Core Helper: Find point in routeGeometry ---
    function findNearestIndex(point, geometry) {
        let minDist = Infinity;
        let index = 0;
        geometry.forEach((p, i) => {
            const d = Math.pow(p[0] - point.lat, 2) + Math.pow(p[1] - point.lon, 2);
            if (d < minDist) { minDist = d; index = i; }
        });
        return index;
    }

    // --- Path Animation Logic ---
    async function animatePath(startIndex, endIndex) {
        if (startIndex === endIndex) return;
        
        const direction = startIndex < endIndex ? 1 : -1;
        const totalSteps = Math.abs(endIndex - startIndex);
        
        const stepDelay = Math.max(8, 35 / SPEED_FACTOR); 
        
        for (let i = 0; i <= totalSteps; i++) {
            if (!window.isStoryPlaying) return;
            const currentIdx = startIndex + (i * direction);
            const pos = routeGeometry[currentIdx];
            if (!pos) continue;
            
            // Calculate rotation for the icon
            if (i > 0) {
                const prev = routeGeometry[startIndex + ((i-1) * direction)];
                if (prev) {
                    const angle = Math.atan2(pos[0] - prev[0], pos[1] - prev[1]) * 180 / Math.PI;
                    const iconEl = storyMarker.getElement().querySelector('.story-marker-icon');
                    if (iconEl) iconEl.style.transform = `rotate(${angle + 90}deg)`;
                }
            }

            storyMarker.setLatLng(pos);
            if (window.storyPath) window.storyPath.addLatLng(pos);
            
            if (i % 25 === 0 && !map.getBounds().pad(-0.1).contains(pos)) {
                map.panTo(pos, { animate: true, duration: 0.4 });
            }
            
            await new Promise(r => setTimeout(r, stepDelay));
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
        
        // 1. Zoom to Station
        map.setView([s.lat, s.lon], 14, { animate: true, duration: 0.8 });
        storyMarker.setLatLng([s.lat, s.lon]);
        await new Promise(r => setTimeout(r, 900));

        // 2. Show Info Card
        const cardAnchor = document.getElementById('story-card-anchor');
        cardAnchor.innerHTML = `
            <div class="story-card animate__animated animate__fadeInUp">
                ${s.image_url ? `<img src="${s.image_url}" class="story-card-img">` : ''}
                <div class="story-card-body">
                    <div class="story-card-meta">
                        <span class="badge bg-warning text-dark">${s.date_str}</span>
                        <span class="text-secondary opacity-75 small">${s.location}</span>
                    </div>
                    <h5 class="story-card-title">${s.is_event ? s.title : 'Tagebuch-Eintrag'}</h5>
                    <p class="story-card-text">${s.description || 'Schöner Tag in ' + s.location}</p>
                </div>
            </div>
        `;

        document.getElementById('story-progress-fill').style.width = `${((currentIndex + 1) / stations.length) * 100}%`;

        await new Promise(r => setTimeout(r, WAIT_STATION)); 

        const card = cardAnchor.querySelector('.story-card');
        if (card) { card.classList.replace('animate__fadeInUp', 'animate__fadeOutDown'); }
        await new Promise(r => setTimeout(r, 600));

        // 4. Move to next point along the route
        if (nextS && routeGeometry.length > 0) {
            const idx1 = findNearestIndex(s, routeGeometry);
            const idx2 = findNearestIndex(nextS, routeGeometry);
            
            map.fitBounds([[s.lat, s.lon], [nextS.lat, nextS.lon]], { padding: [120, 120], animate: true, duration: 0.8 });
            await new Promise(r => setTimeout(r, 900));
            
            await animatePath(idx1, idx2);
        }

        currentIndex++;
        playNextWaypoint();
    }

    playNextWaypoint();
};

window.stopStoryMode = function() {
    window.isStoryPlaying = false;
    if (window.activeStoryMarker) window.activeStoryMarker.remove();
    if (window.storyPath) { window.storyPath.remove(); window.storyPath = null; }
    const overlay = document.getElementById('story-overlay');
    if (overlay) overlay.remove();
    
    // UI RESTORE
    document.getElementById('btn-start-story')?.classList.remove('d-none');
    const activeControls = document.getElementById('story-active-controls');
    if (activeControls) {
        activeControls.classList.add('d-none');
        activeControls.classList.remove('d-flex');
    }
    showToast("🎬 Story beendet.");
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
