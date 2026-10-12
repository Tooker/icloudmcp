# Prüfung: weitere Funktionen aus pyicloud

Umsetzungsstand 12. Oktober 2026: Drive verwendet die hier geprüften
Leseendpunkte direkt über HTTPX. Der vorhandene administrative Go-Login ist
um Drive-Erkennung, gezielte Gerätefreigabe und einen geschützten Export
erweitert; pyicloud ist keine Laufzeit- oder Anmeldeabhängigkeit. Details:
[Drive-Konzept](icloud-drive-concept.md).

Stand: 11. Oktober 2026. Quellcodevergleich und Architekturvorschlag;
keine Abhängigkeit installiert, keine Laufzeitänderung und kein Live-Test.
Die Prioritäten sind unsere Einschätzung für dieses Projekt.

Geprüft wurden `timlaing/pyicloud` am Commit
[`78f459c623735018b9a2801b64f22f3a15cc0c77`](https://github.com/timlaing/pyicloud/tree/78f459c623735018b9a2801b64f22f3a15cc0c77)
und das veröffentlichte [Release 2.7.0](https://github.com/timlaing/pyicloud/releases/tag/2.7.0)
am Commit `86c4bc90d5632bcaf7507e5335e127f7450a177a`.
Die betrachteten öffentlichen pyicloud-Methoden sind in beiden Ständen vorhanden.
Die Korrekturen dazwischen sind trotzdem relevant: Besitzeradressierung
beim Download geteilter Drive-Dateien und vollständige Beziehungen
verschachtelter Notizordner wurden nach 2.7.0 geändert. Eine spätere
Integration muss den gewählten Stand ausdrücklich festlegen.

**Nützliche zusätzliche Bereiche**

| Bereich | Vorhandene Bausteine | Einordnung für unser MCP |
| --- | --- | --- |
| Drive | Ordner und Metadaten, Datei-Downloads, Upload, Verschieben, Umbenennen, Papierkorb und Wiederherstellung. | Erster Prototyp; Grundlage des [Drive-Konzepts](icloud-drive-concept.md). |
| Notizen | Ordner, aktuelle Notizen, Textdecodierung, Anhänge, HTML-Darstellung und Änderungsabfragen mit Sync-Cursor. | Hoher Nutzen nach Drive: Notizen finden, lesen und Anhänge als MCP-Dateien ausgeben. |
| Kontakte | pyicloud liest alle Kontakte und die eigene Kontaktkarte. | Gewünscht sind Lesen und Erstellen; dafür wird [CardDAV als gemeinsamer Zugang](icloud-contacts-concept.md) vorgeschlagen. |
| Weitere Reminders-Felder | Tags, Wiederholungsregeln, Ortsalarme, URL-/Bild-Anhangsmodelle und Markierungen. | Protokollreferenz für gezielte Erweiterungen unseres bestehenden Go-Backends. |
| Fotos | Bibliotheken, Alben, Metadaten, Downloads, Änderungsabfragen und zusätzliche Mutationen. | Eigenes späteres Modul; zunächst Alben und begrenzte Dateiabrufe. |
| „E-Mail-Adresse verbergen“ | Aliasse lesen, generieren/reservieren, beschriften, deaktivieren und reaktivieren. | Nützliche Ergänzung zur Mailverwaltung, falls der Dienst im Account angeboten wird. |
| Apple Invites | Eigene/geteilte Einladungen lesen, Teilnehmerantworten lesen, Einladung auflösen/annehmen und RSVP ändern. | Optional für Nutzer von Apple Invites; eigene Datenquelle neben Kalenderterminen. |
| Speicher und Geräte | Account-Speichernutzung sowie Geräteinformationen und Find-My-Funktionen. | Speicherübersicht gut als Zusatz; Geräte-/Standortzugriff nur als gesondert gewählter Umfang. |

Quellen für Dateizugriff:
[Drive-Service](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/drive.py)
und [Besitzeradressierung bei geteilten Downloads](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/tests/test_shared_owner_downloads.py).
Der Test nutzt synthetische Antworten und belegt keine Live-Kompatibilität.

Weitere Quellen:
[Fotos](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/photos_cloudkit/service.py),
[Mail-Aliasse](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/hidemyemail.py),
[Apple Invites](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/invites/service.py),
[Account-Speicher](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/account.py)
und [Find My](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/findmyiphone.py).

**Notizen und Kontakte konkret**

Die größte eingesparte Eigenentwicklung bei Notizen wäre die Decodierung
von Apples strukturierten Dokumenten samt Anhangsmodellen. Die vorhandene
Service-Schicht bietet Lese-/Exportfunktionen, keine öffentliche
Erstellen-/Bearbeiten-API. Erste MCP-Werkzeuge wären `list_note_folders`,
`list_notes`, `search_notes`, `get_note` und `get_note_attachment`.
Titelsuche kann den Ansatz der vorhandenen CLI verwenden; Inhaltssuche
benötigt einen eigenen lokalen Index. Der Notiz-Service verwendet derzeit
den privaten CloudKit-Scope. Geteilte Notizen werden daher nicht pauschal
zugesagt; passwortgesperrte Notizen liefern einen eigenen Fehler.
Quelle:
[Notiz-Service](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/notes/service.py).

Die Kontaktklasse bietet `all`, `me` und einen Refresh, keine öffentliche
Schreib-API. Der Nutzer möchte auch Kontakte erstellen; der
[Kontaktentwurf](icloud-contacts-concept.md) sieht deshalb einen gemeinsamen
CardDAV-Zugang für Lesen, Suchen und `create_contact` vor. pyicloud bleibt
eine Vergleichsquelle für Kontaktfelder. Seine Kontaktabfrage lädt alle
Kontakte; ein begrenztes MCP-Ergebnis begrenzt daher nicht automatisch den
entfernten Abruf. Mehrdeutige Namen bleiben mehrere Treffer. Kontakte liefern
keine gültigen Reminders-Teilnehmer-IDs: Zuweisungen nutzen weiterhin die
Teilnehmer der konkreten geteilten Liste.
Quelle:
[Kontakt-Service](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/contacts.py).

**Was für bestehende Dienste verwendbar ist**

Calendar bleibt bei CalDAV, Mail bei IMAP und Reminders beim spezialisierten
Go-Backend. Die aktuelle Python-MCP-Schicht enthält bereits die für uns
wichtigen Regeln zu einzelnen Kalender-Vorkommen, vollständigen Anhängen,
geteilten Reminder-Listen, Strukturänderungen und ungewissen Schreibresultaten.

Bei Reminders lohnt die Übernahme der Protokollkenntnisse für neue Felder
und verknüpfte Datensätze. Die untersuchte Implementierung schreibt mit
einer festen `Reminders`-Zone. Ihr Generator für `ResolutionTokenMap`
erzeugt für bearbeitete Felder neue Replica-IDs mit Zähler 1. Für bestehende
Datensätze benötigen wir dagegen die Erhaltung nativer Replica-IDs,
Zähler und unbekannter Metadaten sowie die ursprüngliche Besitzerzone.
Neue Reminders-Funktionen werden deshalb im bestehenden Go-Schreibpfad
mit dessen Metadaten- und Berechtigungsprüfung implementiert.
Quellen:
[Zusätzliche Reminders-Methoden](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/reminders/service.py),
[Zonenkonstanten](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/reminders/_constants.py)
und [Token-Generator](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/reminders/_protocol.py).

**Gemeinsame technische Bausteine**

- Anmeldung: SRP, 2FA und gespeicherte Cookies/Sitzungen sind vorhanden.
  Ein optionaler privater Python-Backend-Dienst könnte eine Websession für
  Drive, Notizen und später Fotos besitzen. Er hat genau einen Besitzer der
  Sitzungsdateien und serialisiert Zugriffe auf die veränderliche Sitzung.
  Das aktuelle Go-Backend behält seinen eigenen Sitzungsbesitzer.
- Gerätefreigabe: Die High-Level-Properties `drive`, `notes`, `photos` und
  `reminders` rufen selbst den PCS-Freigabefluss auf. Unter ADP kann dabei
  eine Gerätebenachrichtigung ausgelöst werden. Unsere Integration trennt
  administrative Freigabe und normale Werkzeugaufrufe; die unveränderten
  Properties sind dafür nicht unmittelbar geeignet.
- Diagnose: Das Dienstinventar und `icloud doctor` unterscheiden angebotene,
  fehlende oder ungültige Service-Endpunkte. Für MCP übernehmen wir nur
  sichere Statusangaben; Accountnamen, Sitzungspfade und URLs werden aus
  dem Bericht entfernt. Ein angebotener Endpunkt belegt noch keine
  tatsächliche Datenfreigabe.
- CloudKit: Typisierte Modelle, paginierte Abfragen, Asset-Streams und
  Sync-Cursor sparen Transport-/Parsing-Code. Cursor werden account-,
  dienst- und zonengebunden gespeichert. Für einen lokalen Index bleiben
  Erstabdeckung, Löschungen und ungültige Cursor eigene Aufgaben.
- Dateien: Downloads aus Drive und Notizen können die vorhandene native
  MCP-Dateiausgabe nach Verallgemeinerung sowie PDF/Text-Extraktion nutzen.
  Remote-URLs bleiben backendintern; Ergebnisse enthalten opaque IDs.
  Eine Erweiterung der Suche braucht eigene Quelladapter mit stabilen
  Datei-/Notiz-IDs und Versionen. Der Mailindex bleibt auf EML-Quellen begrenzt.

Quellen:
[Anmeldung und automatische PCS-Aufrufe](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/base.py),
[Diagnose](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/diagnostics.py)
und [CloudKit-Transport](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/common/cloudkit/client.py).

pyicloud nutzt synchrones `requests`; seine einzelnen Requests bzw.
CloudKit-Zeitlimits ergeben noch kein Gesamtzeitlimit für ein Werkzeug.
Ein Wrapper setzt ein Gesamtbudget, begrenzt alle Requests einschließlich
Download-Auflösung und Streams, und behandelt ungewisse Schreibresultate
ohne Wiederholung. Ein asyncio-Timeout allein beendet keinen laufenden
blockierenden Request. Die Library protokolliert teils URLs und IDs und
liefert teils Servertexte in Exceptions. Diese Ausgaben werden durch
inhaltfreie Logs und sichere Fehlercodes ersetzt.
Quelle:
[Session-Transport und Fehlerbehandlung](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/session.py).

**Empfohlene Reihenfolge**

1. Drive-Lese-Prototyp inklusive administrativer Anmeldung/Freigabe und
   Download einer ausgewählten Datei; dabei den Library-Stand festlegen.
2. Gemeinsame Sitzung, sichere Diagnose und Dateiablage für Zusatzdienste
   fertigstellen; optionale private Compose-Anbindung.
3. Notizen lesen und Anhänge abrufen; Kontakte über CardDAV lesen, suchen
   und erstellen.
4. Ausgewählte Reminders-Erweiterungen im Go-Backend umsetzen, zuerst
   Metadaten lesen und anschließend native Schreibintegrität prüfen.
5. Fotos, Aliasse und Apple Invites nach tatsächlichem Bedarf ergänzen.

Die Library wird bevorzugt als gepinnte Abhängigkeit eingebunden. Ihre
MIT-Lizenz verlangt bei übernommenem Code die Beibehaltung des
Copyright- und Lizenzhinweises. Quelle:
[pyicloud-Lizenz](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/LICENSE).
