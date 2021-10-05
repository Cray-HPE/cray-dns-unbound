#!/bin/bash

set -e

if [[ "$@" == "" ]]; then
  /srv/unbound/initialize.py
  unbound -c ${UNBOUND_CONFIG_DIRECTORY}/unbound.conf &
  sleep 5 &
  while true; do /srv/unbound/initialize.py; sleep ${DNS_INITIALIZE_INTERVAL_SECONDS}; done
else
  $@
fi
