# Docker images

GitHub Actions baut und testet dieses Projekt auf nativen Linux-Runnern für
AMD64 und ARM64. Erst nach erfolgreichen Projekttests und Container-Prüfungen
werden beide Architekturen zu einem gemeinsamen Image zusammengeführt.

- Registry: `ghcr.io/tooker/icloudmcp`
- Standard-Tag für diese Compose-Datei: `latest`
- Automatische Builds bei Push auf `main` sowie Tags `v*`
- Versionierter Build: `v1.2.3`
- Commit-Build: `sha-<vollständige-Commit-SHA>`
- Einzelarchitektur-Tags `sha-<SHA>-amd64` und `sha-<SHA>-arm64` dienen der Manifest-Erstellung.
- Pull Requests prüfen beide Architekturen, ohne Images zu veröffentlichen.
- Manuelle Builds sind im Workflow **Docker images** möglich. Nur die oben genannten Branches und Versionstags veröffentlichen Images.

## Start und Update

Nach dem Einrichten der lokalen Konfiguration:

```bash
docker compose pull icloud-cruncher
docker compose up -d --no-build icloud-cruncher
```

Die Compose-Datei behält ihren Build-Abschnitt für lokale Entwicklung.
Mit `docker compose build` und anschließend
`docker compose up -d --no-build --pull never` lässt sich ein eigener Build verwenden.
Laufende Dienste werden durch einen GitHub-Build nicht automatisch neu gestartet.

## Build ohne Kontozugangsdaten

Die Workflow-Jobs verwenden ausschließlich Unit-Tests und Container-Prüfungen
ohne externe Dienste. Live-Tests, Kontologins und produktive Schreiboperationen
werden nicht gestartet. Der Registry-Upload verwendet den kurzlebigen
`GITHUB_TOKEN` des Workflows; zusätzliche Registry-Secrets sind nicht nötig.
