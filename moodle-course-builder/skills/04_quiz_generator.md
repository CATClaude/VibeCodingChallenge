# Skill: Quizgenerator
Erzeuge Wissensfragen ausschließlich aus dem vorliegenden Lerninhalt.

Regeln:
- genau eine richtige Antwort
- drei plausible falsche Antworten
- keine Trickfragen
- eindeutige Formulierungen
- kurze Erklärung zur richtigen Antwort

Gib ausschließlich valides JSON aus:
{
  "questions":[
    {
      "question":"...",
      "answers":[
        {"text":"...","correct":true},
        {"text":"...","correct":false},
        {"text":"...","correct":false},
        {"text":"...","correct":false}
      ],
      "explanation":"..."
    }
  ]
}
