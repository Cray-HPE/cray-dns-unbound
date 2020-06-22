#!/bin/bash

set -e

if [[ "$@" == "" ]]; then
  if ! unbound-anchor -a /var/run/unbound/root.key -v | grep 'success'; then
    exit 1
  fi
  /srv/unbound/initialize.py
  unbound -c ${UNBOUND_CONFIG_DIRECTORY}/unbound.conf
else
  $@
fi
