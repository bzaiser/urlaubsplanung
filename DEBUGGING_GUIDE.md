# 🔍 PWA & Mobile Debugging Guide

Wenn es Probleme mit der PWA oder dem Offline-Modus gibt, folge diesen Schritten, um Stunden an Fehlersuche zu sparen:

## 1. Die „Windows-PC-Abkürzung“ (Wichtigster Schritt!)
Wenn die App auf dem iPhone hakt (z.B. weißer Bildschirm), rufe die Seite am Windows-PC im Browser auf:
1. Drücke **F12**, um die Entwickler-Tools zu öffnen.
2. Gehe zum Tab **Console** (Konsole).
3. Achte auf Fehlermeldungen (meist rot). 
   - *Suche nach:* `404`, `Double Slash //`, `ServiceWorker Registration Failed`.
4. Gehe zum Tab **Application** -> **Service Workers** / **Storage**, um den Cache zu prüfen.

## 2. Der „Notaus-Knopf“ (Rescue)
In der App unter **Einstellungen** ganz unten findest du:
- **App-Speicher zurücksetzen**: Löscht den lokalen IndexedDB-Speicher und den Service Worker. Hilft fast immer bei Versions-Konflikten.

## 3. NAS Deployment
Nach jedem Git-Push auf dem NAS immer ausführen:
```bash
bash docker/update-turbo.sh
```

---
*Notiz: Konsolen-Logs am PC sind 10x schneller als Rätselraten am Handy!* 🚐💨✨
