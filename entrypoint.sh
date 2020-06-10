#!/bin/bash

set -e

a_records_path="/opt/unbound/etc/unbound/a-records.conf"

if [[ "$@" == "" ]]; then
  while true; do
    /opt/unbound/update-records.py
    a_records_sum=$(cat ${a_records_path}.sum)
    if [[ "$a_records_sum" != "$(sha256sum ${a_records_path})" ]]; then
      if [ -f /var/run/unbound/unbound.pid ]; then
        echo "Found an updated A records config, restarting unbound..."
        kill -SIGTERM $(cat /var/run/unbound/unbound.pid)
      else
        echo "Starting unbound..."
      fi
      unbound
      sha256sum ${a_records_path} > ${a_records_path}.sum
      echo "Unbound started"
    fi
    sleep 60
  done
else
  $@
fi
