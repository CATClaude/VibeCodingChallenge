# Skill: Abkürzungsverzeichnis

## Ziel
Erzeuge aus einem fertigen Kurs ein präzises Abkürzungsverzeichnis.

## Regeln
- Nimm nur Abkürzungen auf, die im Kurs tatsächlich als Abkürzungen verwendet werden.
- Entferne Dubletten.
- Sortiere alphabetisch.
- Erfinde keine Langformen.
- Eine Langform darf nur angegeben werden, wenn sie aus dem Kursinhalt sicher ableitbar ist.
- Wenn die Langform im Kurs nicht eindeutig ausgeschrieben oder sicher ableitbar ist, verwende exakt:
  "Im Kursmaterial nicht eindeutig ausgeschrieben"
- Begriffe, die lediglich komplett großgeschriebene normale Wörter sind, sind keine Abkürzungen.

## Ausgabe
Gib ausschließlich valides JSON aus:
{
  "abbreviations": [
    {"abbr": "API", "meaning": "Application Programming Interface"}
  ]
}
