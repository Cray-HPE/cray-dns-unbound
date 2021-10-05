#!/bin/bash

set -e

if [[ "$@" == "" ]]; then
  sleep 5
  /srv/unbound/initialize.py
  unbound -c ${UNBOUND_CONFIG_DIRECTORY}/unbound.conf &
  while true; do /srv/unbound/initialize.py; sleep ${DNS_INITIALIZE_INTERVAL_SECONDS}; done
else
  $@
fi
