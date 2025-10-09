#!/bin/sh

if [ "${ENV}" = "development" ]; then
    flask --app "app:create_app('${ENV}')" run --host=${HOSTNAME}
else
    gunicorn -w "${WORKER_COUNT}" -b "${HOSTNAME}":"${SERVICE_PORT}" "app:create_app('${ENV}')"
fi
