#!/usr/bin/env python3

import os
import sys
import json
import requests
import time
import shared

def on_error(err, exit=True):
    print('Error: {}'.format(err))
    if exit:
        sys.exit()

#
# Query Kea for active server lease information
#
time.sleep(3) # a really quick sleep upfront as it'll give our istio-proxy channel out to be ready
              # better chance for a successful first attempt connecting to Kea through the mesh
print('Querying Kea in the cluster to find any updated records we need to set')

kea_headers = {"Content-Type": "application/json"}
kea_request = {"command": "config-get", "service": ["dhcp4"]}

# we'll give some time for connection errors to settle, as this job will work within the
# istio service mesh, and connectivity out through the istio-proxy to kea may take just
# a few. We'll give it about 30 seconds before we fail hard for the job
connection_retries = 0
max_connection_retries = 10
wait_seconds_between_retries = 3
while True:
    try:
        # Convert explicitly to json to catch errors up front.
        kea_request_json = json.dumps(kea_request)

        # Call Kea to retrieve active kea_response
        kea_response = requests.post(url = os.environ['KEA_API_ENDPOINT'],
                                     headers = kea_headers,
                                     data = kea_request_json)
        kea_response.raise_for_status()

        kea_response_json = kea_response.json()
        break
    except Exception as err:
        connection_retries += 1
        message = 'Error connecting to Kea at {} to get leases: {}'.format(os.environ['KEA_API_ENDPOINT'], err)
        if connection_retries <= max_connection_retries:
            print('Kea connection attempt failed: {}'.format(message))
            print('Retrying connection to Kea shortly...')
            time.sleep(wait_seconds_between_retries)
            continue
        else:
            print(message)
            raise SystemExit(err)

kea_return_code = kea_response_json[0]['result']
kea_response_json = kea_response.json()

# It is possible that there are no leases.
if kea_return_code == 3:
    print('No leases found in Kea, exiting.')
    sys.exit()
if kea_return_code != 0:
    print('Kea HTTP call success, but error in results:')
    print('    Return code: {}'.format(kea_return_code))
    print('    Data       : {}'.format(kea_response_json))
    raise SystemExit()

print('Got Kea leases successfully!')

# A main data structure used later
kea_leases = kea_response_json[0]['arguments']['Dhcp4']['reservations']


#
# CASMNET-124: nid -> nid-nmn for v1.3 as nid is HSN
#   TODO - move this to Central DNS after data naming cleanup
#
for lease in kea_leases:
    # looking for any name nid###### from Kea (not found = -1)
    if lease['hostname'].find('nid') > -1:
        lease['hostname'] = lease['hostname'] + '-nmn'


#
# CASMNET-121: Query HSM for CNAME/alias information
#   TODO - move this to Central DNS
#
print('Querying HSM to find any xname records we need to set')
# [
#   {
#     "ID": "b42e99be1a2b",
#     "Description": "Ethernet Interface Lan1",
#     "MACAddress": "b4:2e:99:be:1a:2b",
#     "IPAddress": "10.252.0.28",
#     "LastUpdate": "2020-07-01T21:31:02.126544Z",
#     "ComponentID": "x3000c0s19b1n0",
#     "Type": "Node"
#   }
# ]
hsm_request = 'http://cray-smd/hsm/v1/Inventory/EthernetInterfaces'
connection_retries = 0
max_connection_retries = 10
wait_seconds_between_retries = 3
while True:
    try:
        hsm_response = requests.get(url=hsm_request)
        hsm_response.raise_for_status()
        break
    except Exception as err:
        connection_retries += 1
        message = 'Error connecting to HSM at {} to get xnames: {}'.format(hsm_request, err)
        if connection_retries <= max_connection_retries:
            print('{}, retrying shortly...'.format(message))
            time.sleep(wait_seconds_between_retries)
            continue
        else:
            print(message)
            # Consider this a fatal exception currently to keep all records in sync
            # TODO - should this be non-fatal to allow A-record changes?
            raise SystemExit(err)
hsm_records = hsm_response.json()


#
# Find CNAME records in HSM
#
print('Merging new HSM xnames into Kea lease data structure')
new_records = []
for lease in kea_leases:
    # Skip leases with missing data
    if 'hostname' not in lease or 'ip-address' not in lease:
        continue

    # Not all records in HSM are desired, only those with matching
    # IP addresses and different hostnames - resulting in CNAMES.
    for record in hsm_records:
        # Skip records without data
        if 'IPAddress' not in record or 'ComponentID' not in record:
            continue

        # Skip records with same hostname (expected HSM/Kea duplicates)
        if record['ComponentID'] == lease['hostname']:
            break

        if record['IPAddress'] == lease['ip-address']:
            print('    New CNAME record  {}'.format({'hostname': record['ComponentID'], 'ip-address': record['IPAddress']}))
            print('        Existing A record {}'.format({'hostname': lease['hostname'], 'ip-address': lease['ip-address']}))
            new_records.append({'hostname': record['ComponentID'], 'ip-address': record['IPAddress']})
            break

#
# Merge HSM xnames/CNAMES with Kea lease nid-names.  kea_leases is SoR
#
kea_leases.extend(new_records)


#
# CASMNET-130: UANs need to have <hostname>-mgmt entry to management network
#   TODO - move this to Central DNS expanding use for all Role/SubRole Aliases
#
print('Querying SLS to find UAN records')
# {
#   "Parent": "x3000c0s26b0",
#   "Xname": "x3000c0s26b0n0",
#   "Type": "comptype_node",
#   "Class": "River",
#   "TypeString": "Node",
#   "ExtraProperties": {
#     "Aliases": [
#       "uan01"
#     ],
#     "Role": "Application",
#     "SubRole": "UAN"
#   }
# }
sls_request = 'http://cray-sls/v1/hardware'
connection_retries = 0
max_connection_retries = 10
wait_seconds_between_retries = 3
while True:
    try:
        sls_response = requests.get(url=sls_request)
        sls_response.raise_for_status()
        break
    except Exception as err:
        connection_retries += 1
        message = 'Error connecting to SLS at {} to get records: {}'.format(sls_request, err)
        if connection_retries <= max_connection_retries:
            print('{}, retrying shortly...'.format(message))
            time.sleep(wait_seconds_between_retries)
            continue
        else:
            print(message)
            # Consider this a fatal exception currently to keep all records in sync
            # TODO - should this be non-fatal to allow A-record changes?
            raise SystemExit(err)
sls_records = sls_response.json()

#
# Find UAN CNAME records in SLS
#
print('Merging new SLS UAN names into Kea lease data structure')
new_records = []
# Not all records in SLS are desired, only those with xnames
# where the SubRole is UAN.
for record in sls_records:
    # Skip records without minimal required data
    if 'ExtraProperties' not in record or \
        'Role' not in record['ExtraProperties']:
        continue

    # UAN is an Application SubRole.  Skip records without SubRole.
    # Name aliases need to exist as well.
    if 'SubRole' not in record['ExtraProperties'] or \
        'Aliases' not in record['ExtraProperties']:
        continue

    if record['ExtraProperties']['SubRole'] == 'UAN':
        hmn_xname = record['Parent']
        nmn_xname = record['Xname']

        for lease in kea_leases:
            # Skip leases without hostnames
            if lease['hostname'] == '':
                continue

            # Get the HMN IP address
            if lease['hostname'] == hmn_xname:
                for alias in record['ExtraProperties']['Aliases']:
                    mgmt_alias = alias + '-mgmt'
                    print('    New CNAME record  {}'.format({'hostname': mgmt_alias, 'ip-address': lease['ip-address']}))
                    print('        Existing A record {}'.format({'hostname': lease['hostname'], 'ip-address': lease['ip-address']}))
                    new_records.append({'hostname': mgmt_alias, 'ip-address': lease['ip-address']})

            # Get the NMN IP address
            if lease['hostname'] == nmn_xname:
                for alias in record['ExtraProperties']['Aliases']:
                    print('    New CNAME record  {}'.format({'hostname': alias, 'ip-address': lease['ip-address']}))
                    print('        Existing A record {}'.format({'hostname': lease['hostname'], 'ip-address': lease['ip-address']}))
                    new_records.append({'hostname': alias, 'ip-address': lease['ip-address']})

#
# Merge SLS UAI CNAMES with Kea leases nid-names.  kea_leases is SoR
#
kea_leases.extend(new_records)


#
# Load current running DNS entries
#
print('Loading current DNS entries from configmap')
output = shared.run_command(['kubectl', 'get', 'configmap', os.environ['KUBERNETES_UNBOUND_CONFIGMAP_NAME'], '-n',
    os.environ['KUBERNETES_NAMESPACE'], '-o', 'jsonpath={.data[\'records\\.json\']}'])
try:
    # Main data structure used below
    records = json.loads(output)
except Exception as err:
    raise SystemExit(err)


#
# Match and update a records found in configmap with Kea DHCP entries
#
print('Comparing values and creating new A records config, if changes detected')
# Any proper value in dhcp leases that's not in dns is a diff
# and we will rewrite the config.
# TODO: do we need to account for leases that are removed from DHCP? If so, that's not addressed here
diff = False
for lease in kea_leases:
    # Ignore any Kea lease that doesn't have both a hostname and IP
    if 'hostname' not in lease or 'ip-address' not in lease:
        continue
    create_new = True
    for record in records:
        if lease['hostname'] == record['hostname']:
            create_new = False
            if lease['ip-address'] != record['ip-address']:
                record['ip-address'] = lease['ip-address']
                diff = True
                print('    Existing hostname DNS record to update {} {}'.format(lease['hostname'],lease['ip-address']))
            break
    if create_new:
        records.append({'hostname': lease['hostname'], 'ip-address': lease['ip-address']})
        diff = True
        print('    New hostname DNS record to add {} {}'.format(lease['hostname'],lease['ip-address']))

if diff is True:
    print('    Differences found.  Writing new DNS A records configuration to our configmap.')
    patch_content = '{{"data": {{"records.json": "{}"}}}}'.format(json.dumps(records).replace('"', '\\"'))
    shared.run_command(['kubectl', 'patch', 'configmap', os.environ['KUBERNETES_UNBOUND_CONFIGMAP_NAME'], '-n',
        os.environ['KUBERNETES_NAMESPACE'], '-p', patch_content])
    print('  Running a rolling restart of the deployment...')
    shared.run_command(['kubectl', '-n', os.environ['KUBERNETES_NAMESPACE'], 'rollout', 'restart', 'deployment',
        os.environ['KUBERNETES_UNBOUND_DEPLOYMENT_NAME']])
else:
    print('    No differences found.  Skipping DNS update')
