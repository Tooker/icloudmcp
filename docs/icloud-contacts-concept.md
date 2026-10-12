# Konzept: iCloud-Kontakte lesen und erstellen

Stand: 11. Oktober 2026. Gewünschter Umfang: Kontakte lesen, suchen und
erstellen. CardDAV-Anbindung umgesetzt und mit simulierten DAV-Antworten geprüft;
eine Live-Prüfung mit einem iCloud-Konto steht aus.

**Zugriffsweg**

Für beide Funktionen wird CardDAV als gemeinsamer Backend-Zugang
verwendet. Apple nennt iCloud als Beispiel für einen CardDAV-Container
und dokumentiert App-spezifische Passwörter für Drittanbieterzugriffe auf
Kontakte. CardDAV standardisiert Lesen, Suchen und das Anlegen von vCards.
Quellen:
[Apple: CardDAV-Container](https://developer.apple.com/documentation/contacts/cncontainertype/carddav),
[Apple: App-spezifische Passwörter](https://support.apple.com/de-ch/102654)
und [CardDAV, RFC 6352](https://www.rfc-editor.org/rfc/rfc6352.html).

Damit können Kontakte unabhängig vom geplanten Drive-/Notizen-Webbackend
laufen. Ein eigener `ICloudContactsService` wird direkt in den vorhandenen
Python-MCP eingebunden. Zugangsdaten kommen optional aus `CARDDAV_USERNAME`
und `CARDDAV_APP_PASSWORD`, mit den vorhandenen iCloud-Zugangsdaten als
Fallback. Anmeldung, Discovery und Schreibberechtigungen werden mit dem
konkreten iCloud-Konto geprüft. Ohne Konfiguration bleibt der Dienst optional.

Die geprüfte pyicloud-Kontaktklasse bietet ausschließlich Lesen und einen
Refresh. Sie bleibt eine Vergleichsquelle für Kontaktfelder; für den
gewünschten Umfang ist die gemeinsame CardDAV-Anbindung der erste Kandidat.
Quelle:
[pyicloud-Kontaktklasse](https://github.com/timlaing/pyicloud/blob/78f459c623735018b9a2801b64f22f3a15cc0c77/pyicloud/services/contacts.py).

**Umgesetzte Werkzeuge**

| Werkzeug | Verhalten |
| --- | --- |
| `list_addressbooks` | Verfügbare Adressbücher mit eindeutigen IDs und bekannten Berechtigungen ermitteln. |
| `list_contacts` | Kontakte eines Adressbuchs mit begrenzter Ausgabe auflisten. |
| `search_contacts` | Nach Namen, Organisation, Mailadresse oder Telefonnummer suchen; mehrdeutige Treffer getrennt liefern. |
| `get_contact` | Einen Kontakt anhand seiner ausgegebenen ID mit allen unterstützten Feldern lesen. |
| `create_contact` | Einen neuen Kontakt im ausgewählten schreibbaren Adressbuch erstellen und seine bestätigte ID zurückgeben. |

Für die erste Erstellung werden strukturierte Namen, Anzeigename,
Organisation, mehrere Mailadressen und Telefonnummern mit Labels sowie
Postadressen, vollständiges Geburtsdatum und Notizen vorgesehen. Mindestens
ein verwendbarer Name oder eine Organisation ist erforderlich. Der
vCard-Serializer erzeugt Anzeigename, UID und korrekt maskierte/faltbare
UTF-8-Daten. Bilder, Kontaktgruppen und zusätzliche Apple-Spezialfelder
werden später anhand ihrer nativen Darstellung geprüft.

Ein Adressbuch kann automatisch ausgewählt werden, wenn es genau ein
geeignetes Ziel gibt. Bei mehreren möglichen Zielen ist seine genaue ID
oder eine konfigurierte Standardauswahl nötig. Backend-URLs und freie
Serverpfade sind keine Werkzeugargumente. Kontakt-IDs werden an Account,
Adressbuch und Ressource gebunden; ein Name dient nicht als Identität.

**Erstellen und Ergebnisbestätigung**

Die Erstellung nutzt eine neue vCard-UID und einen dazu gebundenen
Ressourcenpfad. Ein bedingtes `PUT` mit `If-None-Match: *` verhindert das
Überschreiben einer vorhandenen Ressource. Nach bestätigter Erstellung
werden die gespeicherten Daten und der ETag gelesen und zurückgegeben.
Falls diese Nachprüfung scheitert, bleibt die bereits bestätigte Erstellung
im Ergebnis erhalten. Quelle für das Protokoll:
[RFC 6352, Abschnitt 6.3.2](https://www.rfc-editor.org/rfc/rfc6352.html#section-6.3.2).

Namensgleichheit ist erlaubt. Treffer mit derselben Mailadresse oder
Telefonnummer können als mögliche Dubletten angezeigt werden; es erfolgt
keine automatische Zusammenführung. Ein fehlgeschlagenes oder abgebrochenes
Schreiben wird nicht automatisch wiederholt. Bei ungewissem Ergebnis bleiben
UID und Referenz erhalten, damit ein anschließender Leseabgleich denselben
Erstellungsversuch prüfen kann. Eine dauerhafte Request-ID-Zuordnung kann
später Wiederholungen durch MCP-Clients absichern.

Die erste Umsetzung liest ohne Kontakt-Cache direkt vom Server. Spätere
Caches müssen nach Schreiben invalidiert werden und dürfen keine älteren
Refresh-Ergebnisse wieder veröffentlichen. Erstellung ist als Schreibwerkzeug
annotiert und folgt den vorhandenen MCP-Anweisungen für Nutzerfreigaben.

**Integration und Prüfung**

CardDAV-Discovery ermittelt Principal, Adressbuch-Home und tatsächliche
Collections; Partition- und Accountpfade werden nicht geraten. HTTPS bleibt
verifiziert. Redirects und vom Server gelieferte Ressourcenpfade werden vor
dem Weitergeben von Zugangsdaten geprüft. Alle Abfragen haben Zeit-,
Antwortgrößen- und Ergebnismengenlimits. Teilabdeckung wird ausdrücklich
gemeldet. HTTPX übernimmt asynchrone Requests, defusedxml das sichere Lesen
der DAV-Antworten und vobject das Lesen/Serialisieren von vCard 3.0.
pyicloud muss für Kontakte nicht installiert werden.

Logs enthalten nur Operation, Status, Dauer, Fehlerklasse und Mengen.
Kontaktfelder, IDs, vCards, entfernte URLs und Zugangsdaten bleiben daraus
ausgeschlossen. Kontakte ersetzen keine Reminders-Teilnehmer-IDs;
Zuweisungen verwenden weiterhin die Mitglieder der konkreten geteilten Liste.

Automatisierte Tests prüfen Discovery, Adressbuchauswahl, mehrere Feldwerte,
UTF-8/Zeilenmaskierung, begrenzte Suche, Create-Konflikte, bestätigte und
ungewisse Ergebnisse sowie frische Leseabgleiche nach Erstellung. Live-Lesetests bleiben
optional. Ein echter Kontakt wird nur bei ausdrücklich beauftragter
Live-Erstellung angelegt. Die Umsetzung wurde ohne Live-Zugriff geprüft.

Die Bedienung, Feldstruktur, Grenzen und `CARDDAV_*`-Konfiguration stehen im
[README](../README.md#contacts). Drive und Notizen bleiben gesonderte Entwürfe.
