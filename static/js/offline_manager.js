/**
 * Offline Manager for Travel Hub (v28)
 * Clean, safe implementation for background sync and offline storage.
 */

const DB_NAME = 'TravelHubOfflineDB';
const DB_VERSION = 1;
const STORE_NAME = 'pending_diary_entries';

let db;

/**
 * Initializes the IndexedDB for offline diary entries.
 */
async function initDB() {
    return new Promise((resolve, reject) => {
        try {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
                }
            };

            request.onsuccess = (event) => {
                db = event.target.result;
                console.log('📦 PWA: Database initialized.');
                updateSyncIndicator();
                // Start background sync safely without blocking
                initBackgroundSync().catch(err => console.error("Background sync failed to start:", err));
                resolve(db);
            };

            request.onerror = (event) => {
                console.error("Database error:", event.target.error);
                reject(event.target.error);
            };
        } catch (e) {
            console.error("IndexedDB not supported or initialization error:", e);
            reject(e);
        }
    });
}

/**
 * Background synchronization of trip data (diary entries).
 */
async function initBackgroundSync() {
    if (!navigator.onLine) return;
    if (sessionStorage.getItem('pwa_sync_finished_v28')) return;

    const dataEl = document.getElementById('grid-data');
    if (!dataEl) return;

    try {
        const gridDataText = dataEl.textContent.trim();
        if (!gridDataText) return;

        const gridData = JSON.parse(gridDataText);
        // Ensure we have an array
        const dataArray = Array.isArray(gridData) ? gridData : [];
        if (dataArray.length === 0) return;

        const dayIds = [...new Set(dataArray.filter(r => r && r.day_id).map(r => r.day_id))];
        
        if (dayIds.length > 0) {
            synchronizeTripData(dayIds);
        }
    } catch (e) {
        console.warn("PWA: Background synchronization logic skipped (data parsing issue).");
    }
}

async function synchronizeTripData(dayIds) {
    console.log(`PWA: Synchronizing ${dayIds.length} days...`);
    
    for (const id of dayIds) {
        try {
            await fetch(`/day/${id}/diary/`, { headers: { 'HX-Request': 'true' } });
            // Throttle to 400ms
            await new Promise(r => setTimeout(r, 400));
        } catch (e) {
            console.warn(`PWA: Failed to sync day ${id}.`);
        }
    }
    
    sessionStorage.setItem('pwa_sync_finished_v28', 'true');
    console.log("PWA: All trip data synchronized for offline use.");
}

/**
 * Queue an entry for offline submission.
 */
async function queueEntry(dayId, formDataMap, images) {
    if (!db) await initDB();

    const entry = {
        dayId: dayId,
        text: formDataMap.get('text'),
        images: images,
        timestamp: new Date().getTime()
    };

    return new Promise((resolve, reject) => {
        try {
            const transaction = db.transaction([STORE_NAME], 'readwrite');
            const store = transaction.objectStore(STORE_NAME);
            const request = store.add(entry);

            request.onsuccess = () => {
                updateSyncIndicator();
                resolve(true);
            };

            request.onerror = () => reject(request.error);
        } catch (e) {
            reject(e);
        }
    });
}

async function getPendingEntries() {
    if (!db) await initDB();
    return new Promise((resolve, reject) => {
        try {
            const transaction = db.transaction([STORE_NAME], 'readonly');
            const store = transaction.objectStore(STORE_NAME);
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        } catch (e) {
            reject(e);
        }
    });
}

async function removeEntry(id) {
    if (!db) await initDB();
    return new Promise((resolve, reject) => {
        try {
            const transaction = db.transaction([STORE_NAME], 'readwrite');
            const store = transaction.objectStore(STORE_NAME);
            const request = store.delete(id);
            request.onsuccess = () => {
                updateSyncIndicator();
                resolve(true);
            };
            request.onerror = () => reject(request.error);
        } catch (e) {
            reject(e);
        }
    });
}

async function updateSyncIndicator() {
    try {
        const entries = await getPendingEntries();
        const count = entries.length;
        const indicator = document.getElementById('sync-indicator');
        const banner = document.getElementById('offline-sync-banner');

        if (indicator) {
            if (count > 0) {
                indicator.classList.remove('d-none');
                const badge = indicator.querySelector('.badge');
                if (badge) badge.innerText = count;
                indicator.classList.add('text-warning', 'animate-pulse');
            } else {
                indicator.classList.add('d-none');
                indicator.classList.remove('animate-pulse');
            }
        }

        if (banner) {
            if (count > 0 && navigator.onLine) {
                banner.classList.remove('d-none');
                banner.classList.add('animate__fadeInDown');
            } else {
                banner.classList.add('d-none');
            }
        }
    } catch (e) {
        console.warn("Sync indicator update skipped.");
    }
}

async function performSync() {
    try {
        const entries = await getPendingEntries();
        if (entries.length === 0) return;

        console.log(`🔃 Syncing ${entries.length} entries...`);
        let hasError = false;
        let lastErrorStatus = 'Unknown';

        const indicator = document.getElementById('sync-indicator');
        if (indicator) {
            indicator.classList.remove('text-warning', 'text-danger');
            indicator.classList.add('text-info');
        }

        for (const entry of entries) {
            try {
                const formData = new FormData();
                formData.append('text', entry.text);
                
                if (entry.images && entry.images.length > 0) {
                    entry.images.forEach(img => {
                        const file = new File([img.blob], img.name, { type: img.blob.type });
                        formData.append('images', file);
                    });
                }

                const response = await fetch(`/day/${entry.dayId}/diary//`, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-CSRFToken': getCSRFToken(),
                        'HX-Request': 'true'
                    }
                });

                if (response.ok) {
                    await removeEntry(entry.id);
                } else {
                    hasError = true;
                    lastErrorStatus = response.status;
                }
            } catch (error) {
                hasError = true;
                lastErrorStatus = 'Network Error';
            }
        }
        
        if (hasError) {
            if (window.showToast) window.showToast(`⚠️ Synchronisierung unvollständig (${lastErrorStatus})`, true);
            if (indicator) {
                indicator.classList.remove('text-info');
                indicator.classList.add('text-danger');
            }
        } else {
            if (window.showToast) window.showToast("✅ Daten erfolgreich übertragen.");
            if (window.htmx) htmx.trigger('body', 'diaryUpdated');
            updateSyncIndicator();
        }
    } catch (e) {
        console.error("Sync process failed:", e);
    }
}

function getCSRFToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    if (cookieValue) return cookieValue;
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value;
}

// Global listeners
window.addEventListener('online', () => {
    const autoSync = localStorage.getItem('auto_sync_mobile') === 'true';
    if (autoSync) performSync();
    else updateSyncIndicator();
});

document.addEventListener('DOMContentLoaded', () => {
    initDB().catch(err => console.error("Initial DB init failed:", err));
});
