#!/bin/bash

set -ex

if [[ "$@" == "" ]]; then
  /srv/unbound/initialize.py
  unbound -c ${UNBOUND_CONFIG_DIRECTORY}/unbound.conf &
  while true; do /srv/unbound/initialize.py; sleep ${DNS_INITIALIZE_INTERVAL_SECONDS}; done
  #unbound-telemetry tcp --bind --control-interface ${UNBOUND_CONTROL_INTERFACE}:${UNBOUND_PORT}
else
  $@
fi
