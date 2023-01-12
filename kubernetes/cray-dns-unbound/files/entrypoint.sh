#!/bin/bash

set -ex

sleep 5

while true; do /srv/unbound/initialize.py; sleep ${DNS_INITIALIZE_INTERVAL_SECONDS}; done 
