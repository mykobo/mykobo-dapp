#!/bin/bash

if [ "${CIRCLE_BRANCH}" != "main" ]
then
  export IMAGE_TAG=next
else
  export IMAGE_TAG=latest
fi
echo "${IMAGE_TAG}"