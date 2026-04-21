/**
 * Travel Story Renderer (v1.2)
 * Handles the animated trip showcase with path-following and direct-flight fallback.
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
    const ICON_DEFAULT = '🦖'; // T-Rex! 🦖
    const SPEED_FACTOR = 1.8; // Faster flight
    const WAIT_STATION = 2600; // Time spent at each card
    
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

    // Dynamic transport marker (The Dino)
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
                if (window.showToast) showToast("📽️ Aufnahme gestartet (Browser-Tab teilen empfohlen)");
            } else {
                window.isRecording = false;
                recordBtn.classList.replace('btn-danger', 'btn-outline-danger');
                recordBtn.innerHTML = '<i class="bi bi-record-circle-fill"></i><span class="small fw-bold text-uppercase d-none d-md-inline">Rec</span>';
                if (window.showToast) showToast("✅ Video gespeichert.");
            }
        };
    }

    // --- Core Helper: Find point in routeGeometry ---
    function findNearestIndex(point, geometry) {
        if (!geometry || geometry.length === 0) return -1;
        let minDist = Infinity;
        let index = 0;
        geometry.forEach((p, i) => {
            const d = Math.pow(p[0] - point.lat, 2) + Math.pow(p[1] - point.lon, 2);
            if (d < minDist) { minDist = d; index = i; }
        });
        return index;
    }

    // --- Path Animation Logic ---
    async function animatePath(startIndex, endIndex, startCoords, endCoords) {
        let pathPoints = [];
        
        // Use high-res route if available, otherwise direct line fallback
        if (startIndex !== -1 && endIndex !== -1 && routeGeometry.length > 0) {
            const direction = startIndex < endIndex ? 1 : -1;
            const totalSteps = Math.abs(endIndex - startIndex);
            for (let i = 0; i <= totalSteps; i++) {
                pathPoints.push(routeGeometry[startIndex + (i * direction)]);
            }
        } else {
            // FALLBACK: Linear interpolation if no route geometry
            const steps = 60;
            for (let i = 0; i <= steps; i++) {
                const lat = startCoords.lat + (endCoords.lat - startCoords.lat) * (i / steps);
                const lon = startCoords.lon + (endCoords.lon - startCoords.lon) * (i / steps);
                pathPoints.push([lat, lon]);
            }
        }

        if (pathPoints.length < 2) return;
        
        const stepDelay = Math.max(8, 45 / (SPEED_FACTOR * (pathPoints.length / 50))); 
        
        for (let i = 0; i < pathPoints.length; i++) {
            if (!window.isStoryPlaying) return;
            const pos = pathPoints[i];
            
            // Rotation Logic
            if (i < pathPoints.length - 1) {
                const nextPos = pathPoints[i + 1];
                const angle = Math.atan2(nextPos[0] - pos[0], nextPos[1] - pos[1]) * 180 / Math.PI;
                const iconEl = storyMarker.getElement()?.querySelector('.story-marker-icon');
                if (iconEl) iconEl.style.transform = `rotate(${angle + 90}deg)`;
            }

            storyMarker.setLatLng(pos);
            if (window.storyPath) window.storyPath.addLatLng(pos);
            
            // Smoother map follow
            if (i % 20 === 0 && !map.getBounds().pad(-0.2).contains(pos)) {
                map.panTo(pos, { animate: true, duration: 0.6 });
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
        
        // 1. Position Dino and Zoom (only if starting or location changed)
        if (currentIndex === 0) {
            map.setView([s.lat, s.lon], 14, { animate: true, duration: 0.8 });
            storyMarker.setLatLng([s.lat, s.lon]);
        }

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

        // 3. Wait for user to read
        // If next station is same location, wait less
        const isSameLoc = nextS && Math.pow(nextS.lat - s.lat, 2) + Math.pow(nextS.lon - s.lon, 2) < 0.000001;
        const waitTime = isSameLoc ? 1500 : WAIT_STATION;
        await new Promise(r => setTimeout(r, waitTime)); 

        // 4. Transition to next point
        if (nextS) {
            const card = cardAnchor.querySelector('.story-card');
            if (card) { card.classList.replace('animate__fadeInUp', 'animate__fadeOutDown'); }
            await new Promise(r => setTimeout(r, 600));

            if (!isSameLoc) {
                const idx1 = findNearestIndex(s, routeGeometry);
                const idx2 = findNearestIndex(nextS, routeGeometry);
                
                map.fitBounds([[s.lat, s.lon], [nextS.lat, nextS.lon]], { padding: [120, 120], animate: true, duration: 1.0 });
                await new Promise(r => setTimeout(r, 1100));
                
                await animatePath(idx1, idx2, s, nextS);
            } else {
                // Subtle "jump" animation to show we are switching days but staying at location
                const iconEl = storyMarker.getElement()?.querySelector('.story-marker-icon');
                if (iconEl) {
                    iconEl.classList.add('animate__animated', 'animate__bounce');
                    setTimeout(() => iconEl.classList.remove('animate__animated', 'animate__bounce'), 1000);
                }
                await new Promise(r => setTimeout(r, 1000));
            }
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
    const btnStart = document.getElementById('btn-start-story');
    const btnActive = document.getElementById('story-active-controls');
    if (btnStart) btnStart.classList.remove('d-none');
    if (btnActive) {
        btnActive.classList.add('d-none');
        btnActive.classList.remove('d-flex');
    }
    if (window.showToast) showToast("🎬 Story beendet.");
};
