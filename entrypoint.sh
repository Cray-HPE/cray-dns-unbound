#!/bin/bash

set -e

if [[ "$@" == "" ]]; then
  /srv/unbound/initialize.py
  unbound -c ${UNBOUND_CONFIG_DIRECTORY}/unbound.conf
else
  $@
fi
