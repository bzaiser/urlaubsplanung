# Urlaubsplanung 2.0 - Premium Travel Dashboard 🧭🌍

Ein modernes, leistungsstarkes Reiseplanungs-Dashboard auf Django-Basis, das dich von der ersten KI-gestützten Inspiration bis zum fertigen Reisetagebuch begleitet.

## ✨ Highlights

- **🤖 KI-Reise-Designer**: Erstelle komplette 30-Tage-Routen in Sekunden durch einfache Texteingaben (integrierter Prompt-Wizard).
- **📊 Interaktiver Planer**: Verwalte deine Etappen in einer hochperformanten Matrix-Ansicht (AG-Grid Support).
- **📖 Reise-Tagebuch**: Halte Erlebnisse fest und lade Bilder direkt von unterwegs hoch.
- **💰 Finanz-Tracking**: Behalte alle Kosten (geplant vs. gebucht) im Blick, inklusive automatischer Spritkosten-Kalkulation.
- **📱 PWA-Ready**: Installiere die App auf deinem Smartphone für vollen Zugriff am Strand oder im Camper.
- **📅 Smart-Navigation**: Intelligentes Verschieben ganzer Reisen und schnelle Zeitraumanpassung per Knopfdruck.

## 🛠 Tech Stack

- **Backend**: Python 3.12+, Django 5.x
- **Frontend**: HTMX (für Zero-Refresh UX), Alpine.js, Bootstrap 5 (Premium Dark Theme)
- **Database**: SQLite (Standard), PostgreSQL-ready
- **Features**: Progressive Web App (PWA), Google Maps Integration

## 🚀 Installation & Setup

### 1. Repository klonen
```bash
git clone <repository-url>
cd urlaubsplanung
```

### 2. Virtual Environment & Dependencies
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Umgebungsvariablen
Erstelle eine `.env` Datei im Hauptverzeichnis (nutze `.env.example` als Vorlage):
```bash
cp .env.example .env
# Öffne .env und trage deinen SECRET_KEY und ggf. API-Keys ein
```

### 4. Datenbank & Initialisierung
```bash
python manage.py migrate
python manage.py createsuperuser  # Erstelle deinen Admin-Zugang
```

### 5. Server starten
```bash
python manage.py runserver
```

Besuche anschließend `http://127.0.0.1:8000` im Browser.

## ⚙️ Konfiguration

- **AI Wizard**: Gehe in den Bereich "Einstellungen" (im Reise-Menü), um deinen OpenAI API-Key zu hinterlegen (falls direkte API-Anbindung genutzt wird) oder nutze den Prompt-Kopierer für ChatGPT.
- **Checklisten**: Über das Admin-Panel (`/admin`) können Vorlagen für Checklisten (z.B. "Camper-Ausrüstung") importiert werden.

---

*Entwickelt mit ❤️ für Weltenbummler.*
