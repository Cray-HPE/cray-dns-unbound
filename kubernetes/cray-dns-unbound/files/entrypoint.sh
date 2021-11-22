#!/bin/bash

set -e

sleep 5

if [[ "$@" == "" ]]; then
  while true; do /srv/unbound/initialize.py; sleep ${DNS_INITIALIZE_INTERVAL_SECONDS}; done
else
  $@
fi
