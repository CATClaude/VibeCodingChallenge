# Moodle Course Builder

Lokales KI-Autorensystem für automatisch erzeugte, durchklickbare SCORM-1.2-Kurse.

## Ablauf

In **Phase 1** werden nur die Vorgaben gemacht:
- Kurstitel
- exakte Anzahl Inhalts-Slides
- Anzahl Quizfragen
- zusätzliche Hinweise
- Model API
- Quelldokumente
- optional TTS API

Danach startet **Kurs vollständig generieren** automatisch:

1. Dokumentanalyse
2. Slide-Plan mit exakt der vorgegebenen Anzahl
3. vollständige Ausarbeitung jeder einzelnen Slide
4. optional Sprechtext für jede Slide
5. Quiz
6. Abkürzungsverzeichnis

Es werden keine Kapitel oder Module erzeugt. Bei einer Vorgabe von 10 entstehen **exakt 10 Inhalts-Slides + 1 Abkürzungs-Slide**.

## SCORM

Der exportierte Kurs ist keine lange Scroll-Seite. Es ist immer nur **eine Kursseite/Slide gleichzeitig sichtbar**.

Navigation:
- Zurück
- Weiter
- Fortschrittsanzeige
- Seitenzähler
- SCORM lesson_location zum Wiederaufnehmen

Ein vorhandenes Quiz erscheint nach den Inhalts-Slides und der Abkürzungs-Slide als zusätzliche Testseite.

## Model API

Unterstützt:
- Ollama
- OpenAI-kompatible Chat-Completions APIs
- API URL
- Modellname
- optionaler API-Key
- Verbindungstest

## Audio / TTS

Optional OpenAI-kompatible `/audio/speech` API. Wenn aktiviert, erzeugt das System automatisch pro Slide einen editierbaren Sprechtext. Beim SCORM-Export werden die Audiodateien erzeugt und in das Paket eingebettet.

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/CATClaude/VibeCodingChallenge/main/moodle-course-builder/install.sh | bash
```

Standardport:

```text
8090
```

Danach:

```text
http://SERVER-IP:8090
```

Alternativer Port:

```bash
PORT=9000 curl -fsSL https://raw.githubusercontent.com/CATClaude/VibeCodingChallenge/main/moodle-course-builder/install.sh | bash
```

## Moodle

Das erzeugte ZIP als Moodle-Aktivität **Lernpaket (SCORM)** importieren.
