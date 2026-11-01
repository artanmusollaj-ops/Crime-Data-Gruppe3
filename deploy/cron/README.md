# Urban Crime schedule on srv01

Cron invokes the dispatcher every Monday at 04:30 Europe/Zurich:

- first Monday of each month: the normal delta pipeline;
- second Monday: full Chicago and Detroit snapshots, followed by the complete
  pipeline;
- third and fourth Mondays: the normal delta pipeline;
- fifth Monday: no run, so every month has exactly one full and three delta
  runs.

The full run deliberately uses the second Monday. If the first day of a month
is a Monday, the monthly Restic test restore starts at 05:00 and may otherwise
overlap the heaviest pipeline run, including its six-hour `flock` wait window.

Every data run publishes a release, restores and verifies that release,
makes sure the dashboard is running (since 1.11.2026 it replaces
Elasticsearch and Kibana on srv01 and reads the store itself), and finishes
with `serving.pruefe_stand`. The lock prevents scheduled runs from overlapping.

Install or refresh the user crontab:

```bash
mkdir -p logs
crontab deploy/cron/urbancrime.crontab
```

Inspect the schedule and logs:

```bash
crontab -l
tail -f logs/scheduled-pipeline.log
```

Start a run manually:

```bash
docker/srv01-datenlauf.sh delta
docker/srv01-datenlauf.sh full
```

Put the images built by the `Abbilder` workflow into service. The script
resolves the digest behind the moving `:aktuell` tag, writes both lines into
`.env`, pulls, reports the `GIT_COMMIT` baked into the new image and restarts
only what is running. `pipeline` is never restarted: it runs as `run --rm` and
picks up the new image on its next invocation.

```bash
docker/srv01-abbild-einsetzen.sh --trocken   # show what would change
docker/srv01-abbild-einsetzen.sh             # do it
```
