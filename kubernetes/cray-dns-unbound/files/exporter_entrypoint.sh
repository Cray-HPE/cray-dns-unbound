#!/bin/bash

/usr/bin/unbound_exporter -unbound.ca "" -unbound.cert "" -unbound.key "" -unbound.host tcp://${UNBOUND_CONTROL_INTERFACE}:${UNBOUND_CONTROL_PORT}
