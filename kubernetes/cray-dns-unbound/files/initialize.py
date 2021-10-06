#!/usr/bin/env python3
# Copyright 2014-2020 Hewlett Packard Enterprise Development LP

import gzip
import json
import os
import shutil
import signal
import subprocess
import time

# start timer
ts = time.perf_counter()

config_load_file = os.environ['UNBOUND_CONFIG_DIRECTORY'] + '/config_loaded'
check_config_loaded = os.path.isfile(config_load_file)
folder_contents = os.listdir('/configmap/')
config_load_id = ''
reload_configs = False

if not check_config_loaded:
    f = open(config_load_file, 'w')
    f.write(folder_contents[0])
    f.close
    reload_configs = True

if check_config_loaded:
    f = open(config_load_file, 'r')
    config_load_id = f.read()
    f.close

print('Starting check for updates to DNS records')
print('ID for loaded data	{}'.format(config_load_id))
print('ID for mounted data	{}'.format(folder_contents[0]), '\n')

if config_load_id != folder_contents[0]:
    reload_configs = True
    print('Difference in IDs between mounted and loaded data detected\n')

if reload_configs:
    print('Copying data from mounted folder to Unbound config folder.')
    shutil.copyfile('/configmap/records.json.gz', '/etc/unbound/records.json.gz')
    shutil.copyfile('/configmap/unbound.conf', '/etc/unbound/unbound.conf')

    print('Processing data.')
    records_conf = []

    records_json_path = '{}/records.json.gz'.format(os.environ['UNBOUND_CONFIG_DIRECTORY'])
    records_conf_path = '{}/records.conf'.format(os.environ['UNBOUND_CONFIG_DIRECTORY'])

    create_ptr_records = os.environ.get('UNBOUND_CREATE_PTR_RECORDS', 'true')

    print('Reading A records JSON file at {} and translating to {}'.format(records_json_path, records_conf_path))
    with gzip.open(records_json_path, 'rb') as f:
        f_content = str(f.read(), "utf-8")
    f.close()

    records = json.loads(f_content)
    for zone in records:
        if 'true' in create_ptr_records:
            records_conf.extend([
                f'local-data: "{zone["hostname"]} A {zone["ip-address"]}"',
                f'local-data-ptr: "{zone["ip-address"]} {zone["hostname"]}"',
                f'local-data: "{zone["hostname"]}.local A {zone["ip-address"]}"',
                f'local-data-ptr: "{zone["ip-address"]} {zone["hostname"]}.local"'
            ])
        else:
            records_conf.extend([
                f'local-data: "{zone["hostname"]} A {zone["ip-address"]}"',
                f'local-data: "{zone["hostname"]}.local A {zone["ip-address"]}"',
            ])
    f = open(records_conf_path, 'w')
    f.write("\n".join(records_conf))
    f.close()

    print('Processing data completed.\n')
    # reload only if records is not empty
    if len(records) > 0:
        print('Warm reload of Unbound started')
        pid_search = "unbound -c /etc/unbound/unbound.conf"
        ps_out = subprocess.Popen("ps -ef".split(' '), stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE).stdout.read().decode('UTF-8').split(
            "\n")  # Launch command line and gather output
        for entry in ps_out:  # Loop over returned lines of ps
            # print(entry)
            if pid_search in entry:
                unbound_pid = entry.split()[0]  # retrieve second entry in line
                break
        print(' Warm reload of unbound to update configurations')
        print('unbound pid is: {}'.format(unbound_pid))
        print('')
        try:
            os.kill(int(unbound_pid), signal.SIGHUP)
        except Exception as err:
            raise SystemExit(err)
        print('Unbound warm reload completed.')
        print('Warm reload of Unbound completed.\n')

# end timer
te = time.perf_counter()
print('Total time taken to run ({0:.5}s)'.format(te - ts), '\n')
print('Completed check for updates to DNS records\n')
