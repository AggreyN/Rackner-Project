"""alembic/env.py must survive real-world DATABASE_URLs.

URL-encoded password characters (%40 for @, %23 for #) are routine in RDS
connection strings. set_main_option applies configparser interpolation, so an
unescaped % crashes alembic before any DB contact — and since the container
now migrates on boot, that would crash-loop the ECS deployment.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def test_percent_in_database_url_does_not_crash_migrations(tmp_path):
    env = dict(
        os.environ,
        DATABASE_URL=f"sqlite:///{tmp_path}/pct%40test.db",
        APP_ENV="dev",
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "alembic crashed on a %-containing DATABASE_URL (configparser "
        f"interpolation regression):\n{result.stderr[-2000:]}"
    )
