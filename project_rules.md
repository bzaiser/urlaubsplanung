# Project Rules - Urlaubsplanung

## Template Tags
- **STRICT Single Line Rule**: Every single Django template tag (`{% ... %}` or `{{ ... }}`) MUST be contained entirely on a single line. 
  - **NO EXCEPTIONS**: Even if the line becomes extremely long, do NOT split tags across lines.
  - **Reasoning**: Splitting tags breaks the Django template parser.
- **{% trans %} Placement**: Innerhalb von HTML-Elementen muss der `{% trans %}`-Tag immer auf einer **eigenen Zeile** stehen.
- **NO Special Characters in IDs**: In `{% trans "..." %}`-Tags nur eindeutige Schlüssel-Begriffe (z.B. `BTN_ADD_TRIP`) verwenden.

## General Frontend
- **HTMX Focus**: Use HTMX for dynamic content loading and form submissions to ensure a smooth, SPA-like feel.
- **CSS Variables**: Use a centralized design system in `static/css/base.css` with HSL color tokens.
- **PWA Strategy**: Maintenance of `manifest.json` and a Service Worker (`sw.js`) is mandatory for offline support.

## Infrastructure & Environment
- **STRICT: NO Local Docker**: Config files only. No local execution of `docker` commands.
- **KEINE Lokalen Installationen**: Führe niemals `pip install`, `npm install` etc. lokal aus. Alles muss im Container laufen.
- **Deployment**: Synchronisation erfolgt über Git. Der Nutzer führt das Update auf dem NAS aus.

## Troubleshooting & Support
- **Three-Strike Rule**: Wenn ein Problem nach drei Versuchen nicht behoben ist, stoppen und Code-Stellen klar benennen.
