/**
 * Travel Story Renderer (v1.3)
 * Optimized for consistent speed, smart zooming, and T-Rex power.
 */

window.startStoryMode = async function() {
    console.log("🎬 Story Mode (High-Performance) initiated...");
    
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
    const ICON_DEFAULT = '🦖'; 
    const MAX_FLIGHT_DURATION = 4000; // Never fly longer than 4s per segment
    const WAIT_STATION = 3000;       // Dwell time at each waypost
    
    // UI Setup
    const btnStart = document.getElementById('btn-start-story');
    const btnActive = document.getElementById('story-active-controls');
    if (btnStart) btnStart.classList.add('d-none');
    if (btnActive) {
        btnActive.classList.remove('d-none');
        btnActive.classList.add('d-flex');
    }

    const overlay = document.createElement('div');
    overlay.id = 'story-overlay';
    overlay.className = 'story-overlay-container';
    overlay.innerHTML = `
        <div id="story-card-anchor" class="story-card-anchor"></div>
        <div class="story-progress-bar"><div id="story-progress-fill"></div></div>
    `;
    document.body.appendChild(overlay);

    const storyMarker = L.marker([stations[0].lat, stations[0].lon], {
        icon: L.divIcon({
            html: `<div class="story-marker-icon marker-pulse">${ICON_DEFAULT}</div>`,
            className: 'story-marker-container',
            iconSize: [45, 45]
        }),
        zIndexOffset: 1000
    }).addTo(map);

    window.activeStoryMarker = storyMarker;
    window.isStoryPlaying = true;
    
    if (window.storyPath) window.storyPath.remove();
    window.storyPath = L.polyline([], {
        color: 'var(--accent-gold)', weight: 3, opacity: 0.6, dashArray: '5, 10'
    }).addTo(map);

    // Helpers
    function getDistance(p1, p2) {
        const R = 6371; 
        const dLat = (p2.lat - p1.lat) * Math.PI / 180;
        const dLon = (p2.lon - p1.lon) * Math.PI / 180;
        const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                  Math.cos(p1.lat * Math.PI / 180) * Math.cos(p2.lat * Math.PI / 180) * 
                  Math.sin(dLon/2) * Math.sin(dLon/2);
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    }

    function findNearestIndex(point, geometry) {
        if (!geometry || geometry.length === 0) return -1;
        let minDist = Infinity, index = 0;
        geometry.forEach((p, i) => {
            const d = Math.pow(p[0] - point.lat, 2) + Math.pow(p[1] - point.lon, 2);
            if (d < minDist) { minDist = d; index = i; }
        });
        return index;
    }

    /**
     * Optimized Animation: Smooth, time-limited, and orientation-aware.
     */
    async function animatePath(startIndex, endIndex, startCoords, endCoords) {
        let pathPoints = [];
        if (startIndex !== -1 && endIndex !== -1 && routeGeometry.length > 0) {
            const direction = startIndex < endIndex ? 1 : -1;
            const steps = Math.abs(endIndex - startIndex);
            // Thinning: If path is too dense, only use every Nth point for animation smoothness
            const stepSkip = Math.max(1, Math.floor(steps / 100)); 
            for (let i = 0; i <= steps; i += stepSkip) {
                pathPoints.push(routeGeometry[startIndex + (i * direction)]);
            }
            if (pathPoints[pathPoints.length-1] !== routeGeometry[endIndex]) pathPoints.push(routeGeometry[endIndex]);
        } else {
            const steps = 60;
            for (let i = 0; i <= steps; i++) {
                pathPoints.push([
                    startCoords.lat + (endCoords.lat - startCoords.lat) * (i / steps),
                    startCoords.lon + (endCoords.lon - startCoords.lon) * (i / steps)
                ]);
            }
        }

        if (pathPoints.length < 2) return;
        
        // DURATION LOGIC: Long paths shouldn't take forever, short paths shouldn't be too fast
        const dist = getDistance(startCoords, endCoords);
        const duration = Math.min(MAX_FLIGHT_DURATION, Math.max(1200, dist * 50)); 
        const stepDelay = duration / pathPoints.length;
        
        const markerIcon = storyMarker.getElement()?.querySelector('.story-marker-icon');
        if (markerIcon) markerIcon.classList.remove('marker-pulse');

        for (let i = 0; i < pathPoints.length; i++) {
            if (!window.isStoryPlaying) return;
            const pos = pathPoints[i];
            
            if (i < pathPoints.length - 1) {
                const nextPos = pathPoints[i + 1];
                const angle = Math.atan2(nextPos[0] - pos[0], nextPos[1] - pos[1]) * 180 / Math.PI;
                if (markerIcon) markerIcon.style.transform = `rotate(${angle + 90}deg)`;
            }

            storyMarker.setLatLng(pos);
            if (window.storyPath) window.storyPath.addLatLng(pos);
            
            // Map follow (Dynamic threshold based on zoom)
            const currentZoom = map.getZoom();
            const threshold = currentZoom > 12 ? 10 : 30;
            if (i % threshold === 0 && !map.getBounds().pad(-0.15).contains(pos)) {
                map.panTo(pos, { animate: true, duration: 0.5 });
            }
            
            await new Promise(r => setTimeout(r, stepDelay));
        }
        if (markerIcon) markerIcon.classList.add('marker-pulse');
    }

    let currentIndex = 0;

    async function playNextWaypoint() {
        if (!window.isStoryPlaying || currentIndex >= stations.length) {
            window.stopStoryMode();
            return;
        }

        const s = stations[currentIndex];
        const nextS = stations[currentIndex + 1];
        
        // 1. Initial Position / Re-focus
        const currentDist = nextS ? getDistance(s, nextS) : 0;
        const targetZoom = currentDist < 10 ? 15 : 14; 

        if (currentIndex === 0) {
            map.setView([s.lat, s.lon], targetZoom, { animate: true, duration: 1.2 });
            storyMarker.setLatLng([s.lat, s.lon]);
            await new Promise(r => setTimeout(r, 1300));
        }

        // 2. Show Card
        const cardAnchor = document.getElementById('story-card-anchor');
        cardAnchor.innerHTML = `
            <div class="story-card animate__animated animate__fadeInUp">
                ${s.image_url ? `<img src="${s.image_url}" class="story-card-img">` : ''}
                <div class="story-card-body">
                    <div class="story-card-meta">
                        <span class="badge bg-warning text-dark">${s.date_str}</span>
                        <span class="text-secondary opacity-100 small fw-bold">${s.location}</span>
                    </div>
                    <h5 class="story-card-title">${s.is_event ? s.title : 'Tagebuch-Eintrag'}</h5>
                    <p class="story-card-text">${s.description || 'Schöner Tag in ' + s.location}</p>
                </div>
            </div>
        `;

        document.getElementById('story-progress-fill').style.width = `${((currentIndex + 1) / stations.length) * 100}%`;

        // 3. Dwell
        const isSameLoc = nextS && getDistance(s, nextS) < 0.05;
        await new Promise(r => setTimeout(r, isSameLoc ? 1500 : WAIT_STATION)); 

        // 4. Move
        if (nextS) {
            const card = cardAnchor.querySelector('.story-card');
            if (card) { card.classList.replace('animate__fadeInUp', 'animate__fadeOutDown'); }
            await new Promise(r => setTimeout(r, 600));

            if (!isSameLoc) {
                const idx1 = findNearestIndex(s, routeGeometry);
                const idx2 = findNearestIndex(nextS, routeGeometry);
                
                // Smart Zoom: If it's a "City Hop" (e.g. < 10km), don't zoom out too far!
                if (currentDist > 10) {
                    map.fitBounds([[s.lat, s.lon], [nextS.lat, nextS.lon]], { padding: [120, 120], animate: true, duration: 1.2 });
                    await new Promise(r => setTimeout(r, 1300));
                } else {
                    // Local movement: ensure we are close enough to see the Dino
                    if (map.getZoom() < 14) map.setZoom(15, { animate: true });
                    await new Promise(r => setTimeout(r, 500));
                }
                
                await animatePath(idx1, idx2, s, nextS);
            } else {
                // Bounce to show it's a new day card but same place
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
