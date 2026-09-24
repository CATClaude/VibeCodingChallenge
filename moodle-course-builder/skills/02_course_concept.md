# Skill: Kurskonzept
Erstelle aus Analyse und Quellenmaterial ein didaktisch sinnvolles Kurskonzept.

Anforderungen:
- klare Lernziele
- modularer Aufbau
- kurze Lerneinheiten
- Praxisbeispiele
- Wissenschecks
- Quellen pro Abschnitt
- nur quellenbasierte Fachinhalte
- keine erfundenen Organisationsregeln

Gib ausschließlich valides JSON aus:
{
  "course_title":"...",
  "course_description":"...",
  "target_audience":"...",
  "learning_objectives":["..."],
  "modules":[
    {
      "id":"m1",
      "title":"...",
      "objective":"...",
      "sections":[
        {
          "id":"s1",
          "title":"...",
          "content_plan":"...",
          "interaction":"text|example|quiz|checklist",
          "sources":["Dateiname"]
        }
      ]
    }
  ]
}
