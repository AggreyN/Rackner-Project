#!/bin/sh
# Migrate, then serve. ECS tasks boot against a database whose schema may be
# behind — or, on first deploy, entirely absent. Retry briefly because RDS can
# be unreachable in a task's first seconds; if migrations still fail, exit
# nonzero so ECS restarts the task instead of serving a wrong-schema DB.
#
# Every failed attempt prints the tail of alembic's own output — the task's
# last log lines must name the real cause (bad password, missing database,
# unreachable host), not just "gave up". Burying the psycopg error behind a
# retry counter has already cost one debugging round-trip.

LOG=/tmp/alembic-boot.log
attempt=1
while :; do
  if alembic upgrade head >"$LOG" 2>&1; then
    cat "$LOG"
    break
  fi
  echo "=== alembic upgrade head FAILED (attempt $attempt of 5) — underlying error: ===" >&2
  tail -40 "$LOG" >&2
  if [ "$attempt" -ge 5 ]; then
    echo "giving up after $attempt attempts; the error above is the real cause" >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 5
done

# exec so uvicorn is PID 1 and receives ECS's SIGTERM directly.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
