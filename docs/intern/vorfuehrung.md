# Vorführung: Kibana aus Google Cloud

Auf `srv01` ersetzt seit dem 1.11.2026 das eigene Dashboard Kibana;
Elasticsearch und Kibana sind dort seit dem 6.11.2026 entfernt (C-9). Für die Vorführung kommen sie aus der Google-Cloud-Probe und sind über
`srv01` unter **https://urbancrime-kibana.datenwerft.ch** erreichbar, hinter
Cloudflare Access wie die übrigen Dienste. Das eigene Dashboard, die
Einstiegsseite und JupyterLab laufen weiter dauernd auf `srv01` und brauchen
nichts davon.

Diese Datei hält nur die Handgriffe fest. Wie es gebaut ist, steht in
[`storage-architektur.md`](../storage-architektur.md), Abschnitt 17, und in
`AENDERUNGEN.md` unter dem 15.11.2026. Den Ablauf der Vorführung selbst
(FR-62 bis FR-65) gibt es noch nicht; er gehört hierher, wenn er steht.

## Vorher: Kibana starten

Etwa 10 Minuten vor Beginn, auf dem eigenen Rechner im Projektverzeichnis:

```bash
GCP_KIBANA_ADRESSE=https://urbancrime-kibana.datenwerft.ch docker/gcp-starten.sh --nur-kibana
```

Das Skript:

1. startet die VM `urbancrime-probe`;
2. kopiert das aktuelle `srv01`-Release nach Cloud Storage, wenn es dort noch
   fehlt (`tools/kopiere_release.py`);
3. startet auf der VM nur Elasticsearch und Kibana;
4. holt das aktuelle Abbild der Strecke (Marke `:aktuell`). Liegt es unter
   einem anderen Digest als `PIPELINE_IMAGE` in der `.env` der VM, sichert
   das Skript die `.env` als `.env.vor-abbild-<UTC-Zeit>` und schreibt den
   neuen Digest hinein. Die Ausgabe nennt alt, neu und den Commit im Abbild,
   sonst „unveraendert“. Scheitert das Ziehen, fehlt auf der VM meist das
   einmalige `docker login ghcr.io`; die `.env` bleibt dann unberührt;
5. setzt das Release ein;
6. lädt Elasticsearch und Kibana nur, wenn das Abbild neu ist oder
   `pruefe_stand` nicht „stimmt“ meldet.

Bis zum 17.11.2026 fehlte Schritt 4: Kibana baute mit dem Abbild, das die
`.env` der VM nannte, und `pruefe_stand` vergleicht nur das Release. So
zeigte Kibana nach FR-27 noch den alten Code und meldete trotzdem „stimmt“.

Gemessen am 15.11.2026:

| Start | Dauer | Was passiert |
| --- | ---: | --- |
| mit neuem Release | rund 8 min | Kopie, Einspielen, Laden von Elasticsearch (4,5 min) |
| Release schon geladen | 2 min 44 s | nur Start und Prüfung |

Fertig ist es, wenn am Ende `pruefe_stand` für Gold, Elasticsearch und Kibana
„stimmt“ meldet.

**Voraussetzungen**, einmal eingerichtet: `gcloud` mit dem Konto
`antonchr@students.zhaw.ch`, die Schlüssel unter `~/.config/urbancrime-probe/`
(`quelle.env`, `hmac.env`, `vm.env`) und der Tunneldienst `kibana` auf
`srv01`.

## Währenddessen

- **Kibana:** https://urbancrime-kibana.datenwerft.ch, Anmeldung über
  Cloudflare Access. Lädt Kibana beim ersten Aufruf nicht ganz („Elastic did
  not load properly“), einmal neu laden (Cmd+Shift+R).
- **Dashboard, Startseite, JupyterLab:** wie immer auf `srv01`.
- **„Definition of plugin … not found“** (etwa `urlForwarding`), auch im
  privaten Fenster: Cloudflare liefert eine kaputte Fassung eines
  Kibana-Bundles aus seinem Cache. Abhilfe: im Cloudflare-Dashboard unter
  Caching → Configuration → Purge Cache → Custom Purge den Hostnamen
  `urbancrime-kibana.datenwerft.ch` leeren, dann neu laden. Mit der Regel im
  nächsten Abschnitt sollte das nicht mehr vorkommen.

## Cloudflare-Cache: einmal einrichten

Kibana schickt seine Bundles mit
`cache-control: public, max-age=31536000, immutable`. Cloudflare darf sie
damit ein Jahr lang am Edge halten, auch eine Fassung, deren Abruf
abgebrochen ist. Am 17.11.2026 war das so, vermutlich seit dem
Tunnelabbruch vom 15.11.: Kibana brach mit „Definition of plugin
urlForwarding not found“ ab, bis der Cache geleert war. Kibana und Traefik
bleiben, wie sie sind. Den Cache für den Kibana-Host schaltet eine Regel ab,
die Christian im Cloudflare-Dashboard selbst einrichtet; das Repository
greift nicht in Cloudflare ein.

1. Cloudflare-Dashboard, Zone `datenwerft.ch` → **Caching → Cache Rules →
   Create rule**.
2. Name: `Kibana ohne Cache`.
3. Bedingung: **Hostname** *equals* `urbancrime-kibana.datenwerft.ch`.
4. Aktion: **Cache eligibility → Bypass cache**. Speichern und
   einschalten.
5. Einmal den Hostnamen leeren (Purge, wie oben), damit nichts Altes liegen
   bleibt.

Prüfen, nach der Anmeldung über Access, in den Entwicklerwerkzeugen des
Browsers (Netzwerk) an einer Datei unter `/…/bundles/`: Der Antwortkopf
`cf-cache-status` zeigt `BYPASS` oder `DYNAMIC`, nicht `HIT`.

## Rückfallweg, wenn `srv01` oder Cloudflare nicht erreichbar ist

Kibana direkt von der VM, ohne `srv01`:

```bash
gcloud compute ssh urbancrime-probe --project urbancrime --zone europe-west6-a \
    --tunnel-through-iap -- -L 5601:localhost:5601 -N
```

Das Terminal bleibt offen. Kibana ist dann unter http://localhost:5601
erreichbar. Das braucht Internet für Google, aber weder `srv01` noch
Cloudflare. Einen Weg ganz ohne Internet (FR-63) gibt es noch nicht.

## Danach: stoppen

```bash
docker/gcp-stoppen.sh
```

Der Zeitplan stoppt die VM ohnehin täglich um 20:00 (Europe/Zurich). Wer
**nach** 20:00 startet, läuft bis zum nächsten Abend. Die Startausgabe nennt
dann „erst morgen um 20:00“. Eine laufende VM kostet rund 0,09 $ pro Stunde;
Disk und Eimer kosten auch gestoppt weiter, zusammen unter 2 $ im Monat.

Ist die VM gestoppt, zeigt die Kibana-URL 502. Der Tunneldienst auf `srv01`
läuft weiter und verbindet beim nächsten Start von selbst.
