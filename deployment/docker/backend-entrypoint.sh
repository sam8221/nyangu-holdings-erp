#!/bin/sh
# Apply database migrations before starting, unless RUN_MIGRATIONS=false.
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Applying database migrations..."
    alembic upgrade head
fi

exec "$@"
