#!/bin/bash

set -ex

# give time for pod to settle
sleep 15

# initialize.py will start unbound if unbound is not already running
while true; do /srv/unbound/initialize.py; sleep ${DNS_INITIALIZE_INTERVAL_SECONDS}; done &
# telemetry for unbound
unbound-telemetry tcp --bind --control-interface ${UNBOUND_CONTROL_INTERFACE}:${UNBOUND_PORT}

