#!/bin/sh

if [ "${ENV}" = "local" ]; then
    flask --app "app:create_app('${ENV}')" run --host="${HOSTNAME}"
else
    gunicorn --workers "${WORKER_COUNT}" --timeout 60 --bind :"${SERVICE_PORT}" "app:create_app('${ENV}')" --error-logfile - --enable-stdio-inheritance
fi
