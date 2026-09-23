# Marketing Platform

Lokale KI-gestützte Plattform, die Dokumente einliest, daraus Marketing-Inhalte erstellt und automatisch eine Marketing-Landingpage generiert. Die KI-Anbindung erfolgt über eine frei konfigurierbare Ollama-API.

## Funktionen

- Projekte anlegen
- Dateien hochladen: PDF, DOCX, TXT, Markdown
- Inhalte extrahieren und zusammenführen
- Ollama-Endpunkt und Modell konfigurieren
- Marketing-Brief generieren
- Landingpage als vollständiges HTML erzeugen
- Website direkt in der Plattform als Preview anzeigen
- Generiertes HTML herunterladen
- Docker-basierter Betrieb

## Schnellstart

1. `.env.example` nach `.env` kopieren.
2. Falls nötig `OLLAMA_MODEL` ändern.
3. Ollama auf dem Host starten und das gewünschte Modell laden, z. B.:

```bash
ollama pull qwen3:8b
ollama serve
```

4. Plattform starten:

```bash
docker compose up --build
```

Frontend: http://localhost:3000  
Backend/API: http://localhost:8000  
Swagger: http://localhost:8000/docs

## Linux / Ollama

Der Backend-Container erreicht den Host über `host.docker.internal`, das durch `extra_hosts: host-gateway` gesetzt wird.

Standard:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:latest
```

Wenn Ollama auf einem anderen Rechner läuft, kann beispielsweise gesetzt werden:

```env
OLLAMA_BASE_URL=http://192.168.1.20:11434
```

## Architektur

- Frontend: React + Vite
- Backend: FastAPI
- Dokumentextraktion: pypdf, python-docx
- KI: Ollama `/api/chat`
- Persistenz MVP: Dateisystem unter `data/projects/`

## Ablauf

1. Projekt anlegen.
2. Quelldokumente hochladen.
3. Marketing-Brief generieren.
4. Landingpage generieren.
5. Preview prüfen und HTML herunterladen.

## Hinweise

Die generierte Website wird in einem sandboxed iframe angezeigt. Vor einer öffentlichen Veröffentlichung sollte das HTML trotzdem geprüft werden. Für Produktion sollten Authentifizierung, Datenbank, Rate-Limits, Virenscan und ein objektbasierter Storage ergänzt werden.
