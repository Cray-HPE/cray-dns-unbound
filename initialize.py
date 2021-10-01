#!/usr/bin/env python3
# Copyright 2014-2020 Hewlett Packard Enterprise Development LP

import gzip
import json
import os
import shutil


config_load_file = os.environ['UNBOUND_CONFIG_DIRECTORY'] + '/config_loaded'
check_config_loaded = os.path.isfile(config_load_file)
folder_contents = os.listdir('/configmap/')
config_load_id = ''
reload_configs = False

if not check_config_loaded:
	f = open(config_load_file, 'w')
	f.write(folder_contents[0])
	f.close

if check_config_loaded:
	f = open(config_load_file, 'r')
	config_load_id = f.read()
	f.close

print ('config_load_id {}'.format(config_load_id))
print ('folder_contents_id {}'.format(folder_contents[0]))

if config_load_id != folder_contents[0]:
	reload_configs = True

print (reload_configs)

if reload_configs:
	shutil.copyfile('/configmap/records.json.gz', '/etc/unbound/records.json.gz')
	shutil.copyfile('/configmap/unbound.conf', '/etc/unbound/unbound.conf')

	records_conf = []

	records_json_path = '{}/records.json.gz'.format(os.environ['UNBOUND_CONFIG_DIRECTORY'])
	records_conf_path = '{}/records.conf'.format(os.environ['UNBOUND_CONFIG_DIRECTORY'])

	create_ptr_records = os.environ.get('UNBOUND_CREATE_PTR_RECORDS','true')

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
