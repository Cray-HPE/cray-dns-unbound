#!/bin/bash

set -e

a_records_path="${UNBOUND_CONFIG_DIRECTORY}/a-records.conf"
pid_path="/var/run/unbound/unbound.pid"

if [[ "$@" == "" ]]; then
  if ! unbound-anchor -a /var/run/unbound/root.key -v | grep 'success'; then
    exit 1
  fi
  /srv/unbound/initialize.py
  unbound -c ${UNBOUND_CONFIG_DIRECTORY}/unbound.conf
else
  $@
fi
