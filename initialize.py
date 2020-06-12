#!/usr/bin/env python3

import json
import os

a_records_conf = ''

a_records_json_path = '{}/a-records.json'.format(os.environ['UNBOUND_CONFIG_DIRECTORY'])
a_records_conf_path = '{}/a-records.conf'.format(os.environ['UNBOUND_CONFIG_DIRECTORY'])

print('Reading A records JSON file at {} and translating to {}'.format(a_records_json_path, a_records_conf_path))
with open(a_records_json_path) as f:
    a_records = json.loads(f.read())
    for a_record in a_records:
        a_records_conf = '{}local-data: "{} A {}"\nlocal-data-ptr: "{} {}"\n'.format(
            a_records_conf, a_record['hostname'], a_record['ip'], a_record['ip'], a_record['hostname'])

with open(a_records_conf_path, 'w') as f:
    f.write(a_records_conf)
