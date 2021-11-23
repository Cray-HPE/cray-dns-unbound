#!/bin/bash

set -e

# give time for pod to settle
sleep 15

# initialize.py will start unbound if unbound is not already running
while true; do /srv/unbound/initialize.py; sleep ${DNS_INITIALIZE_INTERVAL_SECONDS}; done
