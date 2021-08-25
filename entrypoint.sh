#!/bin/bash

set -ex

if [[ "$@" == "" ]]; then
  /srv/unbound/initialize.py
  unbound -c ${UNBOUND_CONFIG_DIRECTORY}/unbound.conf &
  unbound-telemetry tcp --bind --control-interface ${UNBOUND_CONTROL_INTERFACE}:${UNBOUND_PORT}
else
  $@
fi
