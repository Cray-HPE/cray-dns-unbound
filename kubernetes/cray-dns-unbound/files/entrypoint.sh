#!/bin/bash

set -ex

sleep 5

while true; do /srv/unbound/initialize.py; sleep ${DNS_INITIALIZE_INTERVAL_SECONDS}; done &
unbound-telemetry tcp --bind --control-interface ${UNBOUND_CONTROL_INTERFACE}:${UNBOUND_PORT}
