#!/usr/bin/env python3
# Copyright 2014-2020 Hewlett Packard Enterprise Development LP

import gzip
import json
import os
import shutil

records_conf = ''

records_json_path = '{}/records.json.gz'.format(os.environ['UNBOUND_CONFIG_DIRECTORY'])
records_conf_path = '{}/records.conf'.format(os.environ['UNBOUND_CONFIG_DIRECTORY'])

print('Reading A records JSON file at {} and translating to {}'.format(records_json_path, records_conf_path))
with gzip.open(records_json_path) as fin:
    shutil.copyfileobj(fin, fout)
    records = json.loads(fout.read())
    for zone in records:
        records_conf = '{}local-data: "{} A {}"\nlocal-data-ptr: "{} {}"\n'.format(
            records_conf, zone['hostname'], zone['ip-address'], zone['ip-address'], zone['hostname'])
        records_conf = '{}local-data: "{}.local A {}"\nlocal-data-ptr: "{} {}.local"\n'.format(
            records_conf, zone['hostname'], zone['ip-address'], zone['ip-address'], zone['hostname'])

with open(records_conf_path, 'w') as f:
    f.write(records_conf)
