# Skill: Dokumentanalyse
Analysiere die ausgewählten Quelldokumente für einen Lernkurs.

Ermittle Themen, Unterthemen, Definitionen, Regeln, Abläufe, Beispiele, Checklisten,
Lernziele sowie Unklarheiten und Widersprüche. Erfinde keine Fakten.

Gib ausschließlich valides JSON aus:
{
  "title_suggestion":"...",
  "source_summary":"...",
  "documents":[{"name":"...","summary":"...","topics":["..."]}],
  "topics":[{"name":"...","key_points":["..."],"sources":["Dateiname"]}],
  "learning_objectives":["..."],
  "uncertainties":["..."]
}
