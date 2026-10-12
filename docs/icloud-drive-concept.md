# Konzept: iCloud Drive über MCP

Stand: 12. Oktober 2026. Lesender MCP-Ausbau umgesetzt, mit simulierten
Apple-Antworten und einem echten Dateidownload geprüft. Der Live-Test hat
59.831 Originalbytes über den gemeinsamen MCP übertragen und Größe,
SHA-256 sowie die identischen Bytes über `resources/read` bestätigt.
Anmeldung und gezielte Freigabe erfolgten über den erweiterten Go-Teil.
Ordnererstellung, Upload und mehrstufiges Ersetzen sind ebenfalls umgesetzt
und live in einem neu erstellten Testordner geprüft. Die ersetzte Testdatei
hat 57 unveränderte Bytes; SHA-256, eingebettete MCP-Datei und
`resources/read` stimmen überein. Das vorherige Testoriginal liegt im
nativen Papierkorb; bereits vorhandene Dateien wurden nicht verändert.

Die [weitergehende Quellcodeprüfung von pyicloud](pyicloud-reuse-review.md)
bewertet auch Notizen, Kontakte und zusätzliche Reminders-Funktionen sowie
gemeinsame Anmeldung, Gerätefreigabe und Diagnose.

Mit Drive könnte der MCP-Client beispielsweise eine Rechnung finden,
deren PDF lesen und anschließend mit den vorhandenen Werkzeugen eine
Erinnerung anlegen. Auch ein späteres Ablegen eines Mail-Anhangs wäre möglich.

**Zugriff und Anmeldung**

Der Python-Wrapper [timlaing/pyicloud](https://github.com/timlaing/pyicloud#file-storage-icloud-drive)
dokumentiert Ordnerlisten, Dateimetadaten und Downloads sowie Upload,
Ordnererstellung, Umbenennung und Papierkorboperationen. Die Umsetzung
übernimmt dessen geprüfte Drive-Leseendpunkte direkt über asynchrones HTTPX.
Anmeldung und Gerätefreigabe verwenden die vorhandene Go-Implementierung;
pyicloud ist keine Projektabhängigkeit. Diese Funktionen sind noch
keine Bestätigung, dass unser Konto, geteilte Ordner oder Advanced Data
Protection mit ihm funktionieren.

Die vorhandene CalDAV-/IMAP-Konfiguration ist kein belegter Drive-Zugang.
Für den Webservice wird die gespeicherte Go-Web-Anmeldung aus dem
Reminders-Backend verwendet. Anmeldung
und Freigaben erfolgen administrativ außerhalb von MCP-Werkzeugen; der
laufende Dienst verwendet die Sitzung. Das normale Apple-Passwort gehört
weder in die bestehende App-Passwort-Variable noch in Werkzeugargumente.

Bei Advanced Data Protection wird Webzugriff standardmäßig deaktiviert.
Apple beschreibt eine erneute Aktivierung und temporäre Freigabe durch ein
vertrauenswürdiges Gerät. Ein erfolgreicher Login allein belegt deshalb
keinen nutzbaren Drive-Zugriff. Quelle:
[Apple: Webzugriff und Advanced Data Protection](https://support.apple.com/en-gb/108756).

Die geprüfte pyicloud-Implementierung fordert PCS-Zugriff schon beim
Zugriff auf `api.drive` an und kann dabei eine Gerätebenachrichtigung
auslösen. Deshalb importiert der MCP-Laufzeitadapter keinen pyicloud-
Authenticator und kann ausschließlich die erlaubten Leseendpunkte aufrufen.
Auch Go fordert neue Freigaben ausschließlich über den ausdrücklichen
administrativen Schalter `drive-export --approve-web-access` an.

Das benachbarte Go-Projekt `../icloud-reminders-cli` enthält bereits
SRP-Anmeldung, 2FA, Sitzungsspeicherung und administrative Gerätefreigabe.
Die Erweiterung speichert zusätzlich die von Apple angekündigten `drivews`-
und `docws`-Endpunkte. `drive-export` übernimmt den gespeicherten Token und
die Cookies; bei älteren Sitzungen ergänzt ein `accountLogin` mit diesem
Token die Serviceliste, ohne SRP-Anmeldung, 2FA oder Gerätebenachrichtigung.
Der bestehende Freigabeablauf wird für `appName=iclouddrive` wiederverwendet
und durch einen tatsächlichen Lesezugriff auf den Drive-Wurzelordner geprüft.
Die vorhandene Reminders-Freigabe genügt als Nachweis für Drive nicht.

**Einbindung in dieses Projekt**

Drive wird optional hinter dem bestehenden Python-MCP angeboten. Ein
privater Backend-Dienst besitzt seine Sitzung und ein eigenes Volume;
Python stellt typisierte Drive-Werkzeuge bereit. Ein Ausfall oder eine
abgelaufene Drive-Freigabe blockiert weder den Start noch die anderen Dienste.
Die HTTP-Endpunkte bleiben `/healthz`, `/mcp` und `/mcp/`.

Der gewählte eigene Python-Dienst läuft unter dem Compose-Profil `drive`,
mit eigenem `drive-data`-Volume und ohne veröffentlichten Port. Der gemeinsame
MCP verbindet sich über `DRIVE_MCP_URL` und einen eigenen `DRIVE_MCP_TOKEN`.
Der Admin-Befehl exportiert Cookies, Accountkennung und erkannte Endpunkte
atomar in eine private Sitzungsdatei. Das Hauptpasswort wird nicht exportiert.
Der Go-Admin-Dienst erhält dafür beide Volumes, während Reminders gestoppt
ist. Nur Go schreibt die ursprüngliche Anmeldung. Die Laufzeit liest den
separaten Export aus einem nur lesbar eingebundenen Volume; sie öffnet keine
Go-Sitzungsdatei. Cookie-Domain, Hostbindung, Secure-Flag und Ablauf bleiben
erhalten. Sitzungserneuerung und erneute Gerätefreigabe
bleiben ausdrücklich administrative Befehle.

**Umgesetzte Lesewerkzeuge**

| Werkzeug | Verhalten |
| --- | --- |
| `list_drive_items` | Ein Verzeichnis mit begrenzter, paginierter Ausgabe auflisten; IDs, Typ, Größe und Änderungszeit liefern. |
| `search_drive_files` | Nach Namen innerhalb eines angegebenen Ordners suchen; Rekursion und Aufwand begrenzen und unvollständige Ergebnisse kennzeichnen. |
| `get_drive_file` | Eine Datei anhand ihrer ID als native MCP-Datei, extrahierten PDF/Text oder begrenzte Original-Byte-Chunks abrufen. |
| `drive_status` | Konfiguration, Sitzungs-/Freigabestatus und unterstützte Funktionen ohne Accountdaten anzeigen. |

Die Namenssuche ist zunächst eine begrenzte Ordnerdurchsuchung bzw. Suche
über erfasste Metadaten. Eine globale Apple-Suche oder vollständige
Inhaltssuche wird damit nicht zugesagt.

IDs sind verschlüsselte, Account und native Ressource umfassende Referenzen.
Ein gleichbleibender Schlüssel erhält ausgegebene Referenzen über Neustarts
und administrative Erneuerungen desselben Accounts. Metadaten werden vor
und nach Downloads geprüft; weitere Chunks/Textfenster verlangen die
Downloadversion einschließlich des vollständigen Inhaltshashes.
Dateireferenzen enthalten einen geschützten Hinweis auf den Elternordner:
Apple liefert aktuelle Dateimetadaten in dessen frischer Ordnerliste,
während direkte Datei-Abfragen am Ordner-Endpunkt HTTP 500 liefern.
Ältere Referenzen bleiben über eine begrenzte frische Ordnersuche nutzbar;
unvollständige Suche kann keine Abwesenheit belegen.
Geteilte Elemente, App-Bibliotheken und Dokumentpakete werden übersprungen
oder verständlich als nicht unterstützt gemeldet. Teilabdeckung ist sichtbar.

`app/mcp_resources.py` und `app/mail_attachments.py` liefern die Basis für
Dateiausgabe und PDF/Text-Extraktion. Die Ressourcenklasse verwendet jetzt
eine gemeinsame Dateiablage mit getrennten URI-Namensräumen. Die Grenzen
von 64 Snapshots, 30 MB insgesamt und maximal 15 Minuten gelten gemeinsam. Es gibt
keine öffentlichen Downloadrouten und keine Snapshot-Auflistung.

Ein späterer Inhaltsindex benötigt eigene Drive-Quellen mit Datei-ID und
Version. Die bestehende semantische Mailsuche bleibt auf SQLite-EML-Quellen
beschränkt. Inhaltsindexierung für Drive ist eine eigene Entscheidung.

**Umgesetzte Schreibwerkzeuge**

`create_drive_folder`, `upload_drive_file` und `replace_drive_file` erweitern
den bestehenden Adapter. Der geprüfte Uploadablauf stammt aus pyicloud;
die native Etag-Prüfung für Umbenennung und Papierkorb wurde zusätzlich am
[rclone-Quellstand 4f19e9c](https://github.com/rclone/rclone/tree/4f19e9cd6f442282d7fa8d5fdbd28ebb68be1131/backend/iclouddrive)
geprüft. Es werden keine rclone-Anmeldung oder automatischen Wiederholungen übernommen.

Neue Dateien werden unter einem frischen temporären Namen aktiviert,
zurückgelesen und bytegenau geprüft, bevor die native Etag-geschützte
Umbenennung den Zielnamen vergibt. Ersetzen verlangt `confirm=true` und
`expected_version`. Der alte Inhalt bleibt erhalten, bis die neue Datei
vollständig geprüft wurde. Dann wandert das Original mit seiner aktuellen
Etag in den nativen Papierkorb, und die neue Datei übernimmt den Namen.
Der Ablauf ist nicht atomar und gibt eine neue Datei-ID zurück.
Andere Lösch-, Umbenennungs- oder Verschiebewerkzeuge sind nicht freigegeben.

Vor jedem Schreiben werden Berechtigungen und aktuelle Metadaten geprüft.
Keine automatischen Schreibwiederholungen: Ein Timeout kann ein bereits
ausgeführter Schritt sein und wird als ungewisses Ergebnis gemeldet.
Bestätigte Schritte, bekannte Datei-/Ordner-/Reservierungs-IDs und ungewisse
Schritte bleiben im Ergebnis erhalten. Bei ungewissem Papierkorb-Schritt ist
`original_in_trash` null. Für Uploads werden begrenzte Text-/Base64-Eingaben
oder interne Verweise auf bereits abgerufene Mail-/Drive-Dateien verwendet; keine beliebigen lokalen
Serverpfade oder vom Client vorgegebenen Download-URLs.

**Prüfung und Einrichtung**

Automatisierte Tests prüfen Ordnerlisten, begrenzte rekursive Suche,
Datei-/PDF-/Textausgabe, abgelaufene Sitzungen und Freigaben, Größenlimits,
Accountbindung, Versionswechsel und den vollständigen Weg durch beide
MCP-Dienste mit simulierten Apple-Antworten. Der separate, ausdrücklich
aktivierbare Live-Test prüft Originalbytes und `resources/read`, ohne
Schreibzugriffe, Anmeldung oder Freigabe auszulösen.
Go-Tests prüfen die Übernahme alter Sitzungen ohne erneute Anmeldung,
Drive-spezifische Freigabe, sichere Endpunkte und den geschützten Export.
Die Laufzeit fordert bei Ablauf weder Login noch Gerätefreigabe automatisch an.
Logs enthalten nur Operation, Status, Dauer, Fehlerklasse und Mengen, keine
Dateinamen, Pfade, Inhalte, URLs, Cookies oder Zugangsdaten.

Für eine Live-Prüfung sind die Schritte in
[README: Drive setup](../README.md#drive-setup) auszuführen. `drive_status`
prüft danach vorhandenen Zugriff, ohne Freigabeprozesse auszulösen.
