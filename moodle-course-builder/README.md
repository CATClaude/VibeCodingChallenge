# Moodle Course Builder V3

Lokales KI-Autorensystem zur Erstellung fertiger SCORM-1.2-Lernpakete aus vorhandenen Dokumenten.

## Workflow
1. Kursvorgaben festlegen: gewünschte Anzahl Slides/Lerneinheiten und weitere Hinweise; anschließend Dokumente auswählen und analysieren
2. Kurskonzept durch das Sprachmodell unter Berücksichtigung dieser Vorgaben erzeugen
3. Kapitel manuell oder per KI bearbeiten
4. Optional Sprechtexte generieren und über eine TTS-API vertonen
5. Fertiges SCORM-1.2-ZIP exportieren

## Model API
Die Weboberfläche unterstützt:
- Ollama (`/api/chat`)
- OpenAI-kompatible Chat-Completions-APIs (`/chat/completions`)
- frei einstellbare API URL
- Modellname
- optionalen Bearer/API-Key
- Verbindungstest direkt in der Oberfläche

Beispiele:
- Ollama Base URL: `http://localhost:11434`
- OpenAI-kompatible Base URL: `http://localhost:8000/v1`

## Audio / TTS
Im Tab **Audio** können angegeben werden:
- TTS API URL
- TTS-Modell
- Stimme
- Ausgabeformat
- optionaler API-Key
- TTS-Verbindungstest mit abspielbarer Testdatei

Die TTS-Schnittstelle erwartet eine OpenAI-kompatible `/audio/speech` API.

Sobald eine TTS API URL eingetragen ist, erscheint **Sprechtext hinzufügen**. Ist die Option aktiviert, kann pro Kapitel automatisch ein eigener Sprechtext über den LLM-Skill erzeugt und anschließend manuell bearbeitet werden.

Beim SCORM-Export wird jeder vorhandene Kapitel-Sprechtext an die TTS-API gesendet. Die erzeugten Audiodateien werden direkt in das SCORM-ZIP eingebettet und im jeweiligen Kapitel über einen HTML5-Audioplayer angeboten. Zur Laufzeit in Moodle ist dadurch keine TTS-API erforderlich.

## Kursvorgaben
Im ersten Schritt können vor der Analyse festgelegt werden:
- gewünschte Länge als Anzahl **Slides / Lerneinheiten** (1–100)
- freie **weitere Hinweise** an den Konzept-Agenten, z. B. Zielgruppe, didaktischer Stil, Schwerpunktsetzung oder gewünschte Praxisnähe

Der Konzept-Agent erhält diese Angaben explizit und versucht, die Summe aller erzeugten Abschnitte möglichst genau auf die gewünschte Slide-Zahl auszurichten. Zusätzlich wird beim SCORM-Export automatisch eine weitere letzte Slide **Abkürzungsverzeichnis** ergänzt. Damit gilt: gewünschte Slide-Zahl + 1 Abkürzungs-Slide. Die Abkürzungen werden aus den tatsächlich verwendeten Kursinhalten gesammelt, dedupliziert und alphabetisch ausgegeben. Die Vorgaben werden außerdem in lokalen Projektständen und Versionen gespeichert.

## Weitere Funktionen
- Drag-and-drop-Kapitelreihenfolge
- Rich-Text-Editor
- Quellenzuordnung pro Kapitel
- automatische Quiz-Erstellung
- Undo/Redo
- Versionsstände
- Vorschau
- lokale Projektspeicherung im Browser
- SCORM-Score und Abschlussstatus

## Skills
- `01_document_analysis.md`
- `02_course_concept.md`
- `03_content_editor.md`
- `04_quiz_generator.md`
- `05_speech_script.md`
- `06_package_builder.md`

## Installation

Direkt von GitHub:
```bash
curl -fsSL https://raw.githubusercontent.com/CATClaude/VibeCodingChallenge/main/moodle-course-builder/install.sh | bash
```

Oder aus einem Clone:
```bash
cd moodle-course-builder
chmod +x install.sh
./install.sh
```

Danach:
`http://localhost:8080`

## Moodle
Das erzeugte ZIP in Moodle als Aktivität **Lernpaket (SCORM)** importieren.
