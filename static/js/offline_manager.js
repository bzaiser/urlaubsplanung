/**
 * Offline Manager for Travel Hub
 * Handles IndexedDB storage for diary entries and background synchronization.
 */

const DB_NAME = 'TravelHubOfflineDB';
const DB_VERSION = 1;
const STORE_NAME = 'pending_diary_entries';

let db;

// Initialize Database
function initDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
            }
        };

        request.onsuccess = (event) => {
            db = event.target.result;
            console.log('📦 Offline DB initialized');
            updateSyncIndicator();
            resolve(db);
        };

        request.onerror = (event) => {
            console.error('❌ DB Error:', event.target.error);
            reject(event.target.error);
        };
    });
}

// Save an entry to the queue
async function queueEntry(dayId, formDataMap, images) {
    if (!db) await initDB();

    const entry = {
        dayId: dayId,
        text: formDataMap.get('text'),
        images: images, // Array of { name, type, blob }
        timestamp: new Date().getTime()
    };

    return new Promise((resolve, reject) => {
        const transaction = db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.add(entry);

        request.onsuccess = () => {
            console.log('📝 Entry queued for offline sync');
            updateSyncIndicator();
            resolve(true);
        };

        request.onerror = () => reject(request.error);
    });
}

// Get all pending entries
async function getPendingEntries() {
    if (!db) await initDB();
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([STORE_NAME], 'readonly');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

// Remove an entry after successful sync
async function removeEntry(id) {
    if (!db) await initDB();
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.delete(id);
        request.onsuccess = () => {
            updateSyncIndicator();
            resolve(true);
        };
        request.onerror = () => reject(request.error);
    });
}

// Update UI Indicator (Cloud Icon)
async function updateSyncIndicator() {
    const entries = await getPendingEntries();
    const count = entries.length;
    const indicator = document.getElementById('sync-indicator');
    const banner = document.getElementById('offline-sync-banner');

    if (indicator) {
        if (count > 0) {
            console.log(`☁️ Sync-Indicator: Showing ${count} pending entries`);
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
            console.log("🔔 Sync-Banner: Showing banner (online)");
            banner.classList.remove('d-none');
            banner.classList.add('animate__fadeInDown');
        } else {
            banner.classList.add('d-none');
        }
    }
}

// Core Sync Logic
async function performSync() {
    const entries = await getPendingEntries();
    if (entries.length === 0) return;

    console.log(`🔃 Syncing ${entries.length} entries...`);
    let hasError = false;
    let lastErrorStatus = 'Unknown';

    // Update UI to "Syncing" state
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
                console.log(`✅ Entry ${entry.id} synced successfully`);
            } else {
                console.error(`❌ Server rejected sync for entry ${entry.id}: Status ${response.status}`);
                hasError = true;
                lastErrorStatus = response.status;
            }
        } catch (error) {
            console.error(`❌ Network error during sync for entry ${entry.id}:`, error);
            hasError = true;
            lastErrorStatus = 'Network Error';
        }
    }
    
    if (hasError) {
        let errorMsg = `⚠️ Sync fehlgeschlagen (Status: ${lastErrorStatus})`;
        if (lastErrorStatus === 403) {
            errorMsg = "🔒 Sicherheits-Fehler (403): Bitte Seite neu laden oder neu einloggen.";
        }
        showToast(errorMsg, true);
        if (indicator) {
            indicator.classList.remove('text-info');
            indicator.classList.add('text-danger');
        }
    } else {
        showToast("✅ Alle Einträge erfolgreich synchronisiert!");
        if (window.htmx) htmx.trigger('body', 'diaryUpdated');
        updateSyncIndicator();
    }
}

function getCSRFToken() {
    // 1. Try to get from Cookie (Most reliable for Django)
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

    // 2. Fallback to hidden input
    const inputToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (inputToken) return inputToken;

    // 3. Fallback to body hx-headers
    return document.body.getAttribute('hx-headers')?.match(/"X-CSRFToken":\s*"([^"]+)"/)?.[1];
}

// Auto-sync attempt on online event
window.addEventListener('online', () => {
    const autoSync = localStorage.getItem('auto_sync_mobile') === 'true';
    if (autoSync) {
        performSync();
    } else {
        updateSyncIndicator();
    }
});

// Initial Init
document.addEventListener('DOMContentLoaded', initDB);
