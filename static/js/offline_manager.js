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
                // Postpone background sync to give priority to the main UI (Planner)
                setTimeout(() => {
                    initBackgroundSync().catch(err => console.error("Background sync failed to start:", err));
                }, 4000); // 4s delay
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

        // Entschlackung: Only sync a maximum of 5 days in the background to avoid cluttering performance
        const dayIds = [...new Set(dataArray.filter(r => r && r.day_id).map(r => r.day_id))].slice(0, 5);
        
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
            const badge = indicator.querySelector('.badge');
            if (count > 0) {
                indicator.classList.remove('d-none');
                if (badge) {
                    badge.textContent = count;
                    badge.classList.remove('bg-warning');
                    badge.classList.add('bg-danger'); // Red point as requested
                }
            } else {
                indicator.classList.add('d-none');
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

// Auto-Sync on Reconnect
window.addEventListener('online', () => {
    if (window.showToast) showToast("🌐 Verbindung wiederhergestellt. Auto-Sync startet...");
    performSync();
});

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

                const response = await fetch(`/day/${entry.dayId}/diary/`, {
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
            if (window.showToast) window.showToast(`📴 Synchronisierung pausiert. Wir warten auf eine stabilere Verbindung.`, true);
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

/**
 * EMERGENCY RESET: Clears all local PWA data and reloads.
 */
async function resetPWAData() {
    window.resetPWAData = resetPWAData; // Ensure global exposure

    const msg = "⚠️ ACHTUNG: Dies löscht alle lokalen PWA-Daten, den Cache und Cache-Speicher.\n\n" +
                "Nicht synchronisierte Tagebuch-Einträge gehen verloren!\n\n" +
                "Fortfahren?";
    
    if (!confirm(msg)) return;

    try {
        if (window.showToast) showToast("⚙️ Reset wird durchgeführt...", false);

        // 1. Unregister all Service Workers
        if ('serviceWorker' in navigator) {
            const registrations = await navigator.serviceWorker.getRegistrations();
            for (let registration of registrations) {
                await registration.unregister();
                console.log("PWA Reset: SW unregistered");
            }
        }

        // 2. Clear Caches
        if ('caches' in window) {
            const keys = await caches.keys();
            await Promise.all(keys.map(k => caches.delete(k)));
            console.log("PWA Reset: Caches deleted");
        }

        // 3. Delete IndexedDB
        const deleteDBRequest = indexedDB.deleteDatabase(DB_NAME);
        deleteDBRequest.onerror = () => console.warn("PWA Reset: Could not delete IndexedDB");
        deleteDBRequest.onsuccess = () => console.log("PWA Reset: IndexedDB deleted");

        // 4. Clear relevant LocalStorage/SessionStorage
        localStorage.removeItem('pwa_version');
        sessionStorage.removeItem('pwa_sync_finished_v28');
        
        if (window.showToast) showToast("✅ Reset abgeschlossen. Seite wird neu geladen...", false);
        
        // 5. Hard reload
        setTimeout(() => {
            window.location.reload(true);
        }, 1500);

    } catch (e) {
        console.error("PWA Reset failed:", e);
        alert("Fehler beim Reset: " + e.message);
    }
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
