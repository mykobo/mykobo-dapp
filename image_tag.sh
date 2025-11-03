#!/bin/bash
# shellcheck disable=SC2155
export IMAGE_TAG=$(semantic-release version --print-last-released)
echo "${IMAGE_TAG}"
