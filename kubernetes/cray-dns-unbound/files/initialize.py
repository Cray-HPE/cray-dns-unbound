#!/usr/bin/env python3
# Copyright 2014-2022 Hewlett Packard Enterprise Development LP

import gzip
import json
import os
import shutil
import signal
import subprocess
import time
import datetime
import sys

date_time = datetime.datetime.now()
print(date_time.strftime("%Y-%b-%d %H:%M"), '\n')

# start timer
ts = time.perf_counter()

# file checks
config_load_file = os.environ['UNBOUND_CONFIG_DIRECTORY'] + '/config_loaded'
unbound_conf_file = os.environ['UNBOUND_CONFIG_DIRECTORY'] + '/unbound.conf'
records_conf_file = os.environ['UNBOUND_CONFIG_DIRECTORY'] + '/records.conf'
custom_records_conf_file = os.environ['UNBOUND_CONFIG_DIRECTORY'] + '/custom_records.conf'
check_config_loaded = os.path.isfile(config_load_file)
check_unbound_conf_exists = os.path.isfile(unbound_conf_file)
check_records_conf_exists = os.path.isfile(records_conf_file)
check_custom_records_conf_exists = os.path.isfile(custom_records_conf_file)

# configmap data setup
folder_contents = sorted(os.listdir(os.environ['UNBOUND_CONFIGMAP_DIRECTORY']))
config_load_id = ''
reload_configs = False
unbound_cmd = ('unbound -c ' + os.environ['UNBOUND_CONFIG_DIRECTORY'] +  '/unbound.conf &')

# create empty records.conf and unbound.conf if they are missing
if not check_records_conf_exists:
    print('Recreating /etc/unbound/records.conf')
    open(records_conf_file, 'a').close()

if not check_unbound_conf_exists:
    print('Recreating /etc/unbound/unbound.conf')
    open(unbound_conf_file, 'a').close()

if not check_custom_records_conf_exists:
    print('Recreating /etc/unbound/unbound.conf')
    open(custom_records_conf_file, 'a').close()

# make sure unbound pid is running
try:
    unbound_pid = int(subprocess.check_output(["pidof", "unbound"]))
except Exception as err:
    print(f'Unbound PID not detected.  Starting unbound')
    os.system(unbound_cmd)

if not check_config_loaded:
    reload_configs = True

if check_config_loaded:
    f = open(config_load_file, 'r')
    config_load_id = f.read()
    f.close()

print('Starting check for updates to DNS records')
print('ID for loaded data	{}'.format(config_load_id))
print('ID for mounted data	{}'.format(folder_contents[0]), '\n')

if config_load_id != folder_contents[0]:
    reload_configs = True
    print('Difference in IDs between mounted and loaded data detected\n')
else:
    print('No Difference in IDs between mounted and loaded data detected\n')

if reload_configs:
    print('Copying data from mounted folder to Unbound config folder.')
    # If unable to read records.json.gz or unbound.conf from the configmap fail gracefully so Unbound
    # continues running with the existing config instead of going into CrashLoopBackOff because this
    # copy fails.
    try:
        shutil.copyfile(os.environ['UNBOUND_CONFIGMAP_DIRECTORY'] + '/records.json.gz', os.environ['UNBOUND_CONFIG_DIRECTORY'] + '/records.json.gz')
        shutil.copyfile(os.environ['UNBOUND_CONFIGMAP_DIRECTORY'] + '/unbound.conf', os.environ['UNBOUND_CONFIG_DIRECTORY'] + '/unbound.conf')
        shutil.copyfile(os.environ['UNBOUND_CONFIGMAP_DIRECTORY'] + '/custom_records.conf', os.environ['UNBOUND_CONFIG_DIRECTORY'] + '/custom_records.conf')
    except FileNotFoundError:
        print('Unable to load config and records from ConfigMap. Leaving existing configuration in place')
        sys.exit(0)

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
        unbound_pid = 0
        pid_check_tries = 0
        print('Warm reload of Unbound started')
        # check for pid
        try:
            unbound_pid = int(subprocess.check_output(["pidof", "unbound"]))
        except Exception as err:
            time.sleep(5)
            try:
                unbound_pid = int(subprocess.check_output(["pidof", "unbound"]))
            except Exception as err:
                print ("Failed getting Unbound PID twice")
                pass
        if unbound_pid != 0 and isinstance(unbound_pid, int):
            print('Warm reload of unbound to update configurations')
            print('Unbound pid is: {}'.format(unbound_pid))
            try:
                os.kill(int(unbound_pid), signal.SIGHUP)
            except Exception as err:
                raise SystemExit(err)

            # write config version
            f = open(config_load_file, 'w')
            f.write(folder_contents[0])
            f.close()
            print('Warm reload of Unbound completed.\n')
        else:
            print('Did not detect Unbound pid.\n')
            print('This can happen on the first run of initialize.py before Unbound has started.')
    else:
        print('Record data is empty, not reloading Unbound.')


# end timer
te = time.perf_counter()
print('Total time taken to run ({0:.5}s)'.format(te - ts), '\n')
print('Completed check for updates to DNS records\n')
