# Checkmate Replay Hub – Beispielzugdateien

Alle `.txt`-Dateien enthalten nur Züge im Format `Startfeld Zielfeld`, eine Bewegung pro Zeile. Kommentare gehören nicht in die Upload-Dateien.

| Datei | Erwartetes Szenario |
| --- | --- |
| `01_gueltig_schachmatt_schwarz.txt` | gültige kurze Partie, Schachmatt durch Schwarz |
| `02_gueltig_schachmatt_weiss.txt` | gültige kurze Partie, Schachmatt durch Weiß |
| `03_gueltig_unvollstaendig.txt` | bisher gültige, aber abgebrochene Partie – kein Schachmatt und kein Gewinner bestimmbar |
| `04_ungueltig_leeres_startfeld.txt` | Startfeld ist leer |
| `05_ungueltig_falsche_farbe.txt` | Schwarz versucht zu Beginn einen Zug, obwohl Weiß am Zug ist |
| `06_ungueltig_figur_blockiert.txt` | Läufer kann die eigene Bauernreihe nicht überspringen |
| `07_ungueltig_bauer_seitwaerts.txt` | Bauer zieht unerlaubt seitwärts |
| `08_ungueltig_zug_nach_schachmatt.txt` | es folgt ein weiterer Zug, obwohl die Partie bereits mit Schachmatt beendet ist |

Für die erste Ausbaustufe können Rochade, en passant und Bauernumwandlung bewusst als nicht unterstützt behandelt werden.
