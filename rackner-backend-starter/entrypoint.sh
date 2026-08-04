#!/bin/sh
# Migrate, then serve. ECS tasks boot against a database whose schema may be
# behind — or, on first deploy, entirely absent (the exact failure that made
# every DB route 500 while /health stayed green). Retry briefly because RDS
# can be unreachable in a task's first seconds; if migrations still fail,
# exit nonzero so ECS restarts the task instead of serving a wrong-schema DB.

attempt=1
until alembic upgrade head; do
  if [ "$attempt" -ge 5 ]; then
    echo "alembic upgrade head failed after $attempt attempts; giving up" >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  echo "alembic upgrade head failed; retry $attempt of 5 in 5s" >&2
  sleep 5
done

# exec so uvicorn is PID 1 and receives ECS's SIGTERM directly.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
