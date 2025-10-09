#!/bin/sh

if [ "${ENV}" = "development" ]; then
    flask --app "app:create_app('${ENV}')" run
else
    gunicorn -w "${WORKER_COUNT}" -b :"${SERVICE_PORT}" "app:create_app('${ENV}')"
fi
