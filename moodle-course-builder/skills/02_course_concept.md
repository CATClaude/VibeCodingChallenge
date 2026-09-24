# Skill: Slide-Plan

Erstelle aus Analyse und Quellenmaterial direkt die Struktur eines Lernkurses als einzelne Slides.

## Zwingende Regeln
- Erzeuge EXAKT die im Prompt verlangte Anzahl an Inhalts-Slides.
- Erzeuge KEINE Kapitel, Module, Unterkapitel oder verschachtelten Strukturen.
- Jedes Objekt im Array `slides` entspricht genau einer sichtbaren Kursseite.
- Die Abkürzungs-Slide gehört NICHT zur angeforderten Anzahl; sie wird automatisch als zusätzliche letzte Inhaltsseite ergänzt.
- Zusätzliche Benutzerhinweise berücksichtigen.
- Jede Slide braucht einen prägnanten Titel und einen konkreten Inhaltsplan.
- Quellen pro Slide angeben.
- Nur quellenbasierte Fachinhalte verwenden.
- Keine Fakten erfinden.

Gib ausschließlich valides JSON aus:
{
  "course_title": "...",
  "course_description": "...",
  "target_audience": "...",
  "learning_objectives": ["..."],
  "slides": [
    {
      "id": "slide_1",
      "number": 1,
      "title": "...",
      "content_plan": "...",
      "interaction": "text|example|checklist",
      "sources": ["Dateiname"]
    }
  ]
}
