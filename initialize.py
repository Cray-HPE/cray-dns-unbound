#!/usr/bin/env python3
# Copyright 2014-2020 Hewlett Packard Enterprise Development LP

import gzip
import json
import os

records_conf = []

records_json_path = '{}/records.json.gz'.format(os.environ['UNBOUND_CONFIG_DIRECTORY'])
records_conf_path = '{}/records.conf'.format(os.environ['UNBOUND_CONFIG_DIRECTORY'])

print('Reading A records JSON file at {} and translating to {}'.format(records_json_path, records_conf_path))
with gzip.open(records_json_path, 'rb') as f:
    f_content = str(f.read(), "utf-8")
f.close()

records = json.loads(f_content)
for zone in records:
    records_conf.extend([
        f'local-data: "{zone["hostname"]} A {zone["ip-address"]}"',
        f'local-data-ptr: "{zone["ip-address"]} {zone["hostname"]}"',
        f'local-data: "{zone["hostname"]}.local A {zone["ip-address"]}"',
        f'local-data-ptr: "{zone["ip-address"]} {zone["hostname"]}.local"'
    ])
f = open(records_conf_path, 'w')
f.write("\n".join(records_conf))
f.close()