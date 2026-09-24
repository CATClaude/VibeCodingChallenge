# Skill: Kurskonzept
Erstelle aus Analyse und Quellenmaterial ein didaktisch sinnvolles Kurskonzept.

Anforderungen:
- die im Prompt genannte gewünschte Anzahl Slides/Lerneinheiten als Zielwert für die Inhalts-Slides einhalten; die Summe aller sections soll diesem Wert möglichst genau entsprechen
- das Abkürzungsverzeichnis wird NICHT in diese Anzahl eingerechnet; es wird später automatisch als eine zusätzliche letzte Slide ergänzt
- zusätzliche Benutzerhinweise aus den Kursvorgaben berücksichtigen
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
