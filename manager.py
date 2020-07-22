#!/usr/bin/env python3

import os
import sys
import json
import yaml
import requests
import time
import shared
from tempfile import NamedTemporaryFile

#
# Pretty print errors
#
def on_error(err, exit=True):
    print('Error: {}'.format(err))
    if exit:
        sys.exit(1)

#
# Remote calls to Kea, HSM and SLS with wrapper for retry and exceptions
#
def remote_request(remote_type ,remote_url, headers=None, data=None):
    connection_retries = 0
    max_connection_retries = 10
    wait_seconds_between_retries = 3

    remote_response = None
    while True:
        try:
            json_data = json.dumps(data)
            response = requests.request(remote_type,
                                        url = remote_url,
                                        headers = headers,
                                        data = json_data)
            response.raise_for_status()
            remote_response = response.json()
            break
        except Exception as err:
            connection_retries += 1
            message = 'Error connecting to {}: {}'.format(remote_url, err)
            if connection_retries <= max_connection_retries:
                print('Connection attempt failed: {}'.format(message))
                print('Retrying connection shortly...')
                time.sleep(wait_seconds_between_retries)
                continue
            else:
                print(message)
                raise SystemExit(err)
    return remote_response


#
# Give istio-proxy channel a chance to be ready
#
time.sleep(3)


#
# Master data structure for DNS records which *must* exist
#
master_dns_records = []


#
# Query Kea for active server lease information
#
print('Querying Kea in the cluster to find any updated records we need to set')

kea_url = os.environ['KEA_API_ENDPOINT']
# DEBUG
# kea_url = 'http://cray-dhcp-kea-api:8000'
kea_headers = {"Content-Type": "application/json"}
kea_request = {"command": "config-get", "service": ["dhcp4"]}

kea_response_json = remote_request('POST',
                                    kea_url,
                                    headers=kea_headers,
                                    data=kea_request)
kea_return_code = kea_response_json[0]['result']

# It is possible that there are no leases.
if kea_return_code == 3:
    print('No leases found in Kea, exiting.')
    sys.exit(1)
if kea_return_code != 0:
    print('Kea HTTP call success, but error in results:')
    print('    Return code: {}'.format(kea_return_code))
    print('    Data       : {}'.format(kea_response_json))
    raise SystemExit()

# Make sure that Kea is actually returning some leases!
if 'arguments' not in kea_response_json[0] or \
    'Dhcp4' not in kea_response_json[0]['arguments'] or \
    'reservations' not in kea_response_json[0]['arguments']['Dhcp4']:
    print('Error:  Kea API returned successfully, but with no leases.')
    print('        Return code: {}'.format(kea_return_code))
    print('        Return data: {}'.format(kea_response_json[0]['arguments']['Dhcp4']))
    sys.exit(1)

# Kea leases is generally canonical as to what should exit in DNS
print('Got Kea leases successfully!')
kea_leases = kea_response_json[0]['arguments']['Dhcp4']['reservations']


#
# Load Kea leases into the master data structure with some data cleanup
#
for lease in kea_leases:
    # Some nodes might be in discovery
    if 'hostname' not in lease or 'ip-address' not in lease:
        continue

    # Having empty values is a flat out error
    if not lease['hostname'].strip() or not lease['ip-address'].strip():
        print('Error: Kea returned lease with incomplete data.  Skipping {}'.format(lease))
        continue

    # CASMNET-124: change nid to nid-nmn for v1.3 because nid is HSN
    #   TODO - move this to Central DNS after data naming cleanup
    if lease['hostname'].find('nid') > -1:
        host = lease['hostname'] + '-nmn'
        ip = lease['ip-address']
        master_dns_records.append({'hostname': host, 'ip-address': ip})
        continue

    # Load remaining leases 
    host = lease['hostname']
    ip = lease['ip-address']
    master_dns_records.append({'hostname': host, 'ip-address': ip})


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
hsm_records = remote_request('GET', hsm_request)


#
# Find CNAME records in HSM
#
print('Merging new HSM xnames into DNS data structure')
new_records = []
for dns in master_dns_records:
    # Not all records in HSM are desired, only those with matching
    # IP addresses and different hostnames - resulting in CNAMES.
    for hsm in hsm_records:
        # Skip records without data
        if 'IPAddress' not in hsm or 'ComponentID' not in hsm:
            continue

        # Skip records with blank data
        if not hsm['IPAddress'].strip() or not hsm['ComponentID'].strip():
            continue

        # Skip records with same hostname (expected HSM/Kea duplicates)
        if hsm['ComponentID'] == dns['hostname']:
            break

        if hsm['IPAddress'] == dns['ip-address']:
            new_record = {'hostname': hsm['ComponentID'], 'ip-address': hsm['IPAddress']}
            old_record = {'hostname': dns['hostname'], 'ip-address': dns['ip-address']}
            print('    New CNAME {}'.format(new_record))
            print('     A record {}'.format(old_record))
            new_records.append(new_record)
            break

#
# Merge HSM xnames/CNAMES with DNS nid-names.  Kea is generally is SoR
#
master_dns_records.extend(new_records)


#
# CASMNET-130 and CASMNET-137: UANs and Management NCNs need to have 
#   <hostname>-mgmt entry to the hardware management network and
#   <hostname>-nmn for the node management network.
#   the 
#   TODO - move this to Central DNS expanding use for all Role/SubRole Aliases
#
print('Querying SLS to find Management and Application records')
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
sls_records = remote_request('GET', sls_request)

#
# Find UAN and Manager/Worker CNAME records in SLS.
# NOTE:  This is the one place where we are NOT using Kea as SoR because
#        NCNs currently are NOT dynamic/DHCP.
#
print('Merging new SLS Application and Management names into DNS data structure')
new_records = []
# Not all records in SLS are desired, only those with xnames
# where the SubRole is UAN.
for sls in sls_records:
    # Skip records without minimal required data
    if 'ExtraProperties' not in sls or \
        'Role' not in sls['ExtraProperties'] or \
        'Aliases' not in sls['ExtraProperties']:
        continue

    if sls['ExtraProperties']['Role'] == 'Management' or \
        sls['ExtraProperties']['Role'] == 'Application':

        hmn_xname = sls['Parent']
        nmn_xname = sls['Xname']

        for hsm in hsm_records:
            # Skip records with blank entries
            if not hsm['ComponentID'].strip() or not hsm['IPAddress'].strip():
                continue

            # Get the HMN IP address
            if hsm['ComponentID'] == hmn_xname:
                for alias in sls['ExtraProperties']['Aliases']:
                    mgmt_alias = alias + '-mgmt'
                    new_record = {'hostname': mgmt_alias, 'ip-address': hsm['IPAddress']}
                    old_record = {'hostname': hmn_xname, 'ip-address': hsm['IPAddress']}
                    print('    New CNAME {}'.format(new_record))
                    print('     A record {}'.format(old_record))
                    new_records.append(new_record)

            # Get the NMN IP address
            if hsm['ComponentID'] == nmn_xname:
                for alias in sls['ExtraProperties']['Aliases']:
                    nmn_alias = alias + '-nmn'
                    new_record = {'hostname': nmn_alias, 'ip-address': hsm['IPAddress']}
                    old_record = {'hostname': nmn_xname, 'ip-address': hsm['IPAddress']}
                    print('    New CNAME {}'.format(new_record))
                    print('     A record {}'.format(old_record))
                    new_records.append(new_record)

#
# Merge SLS CNAMES with DNS records.
# This is the one place Kea is not SoR.
#
master_dns_records.extend(new_records)


# DEBUG
# print(len(master_dns_records))
# f = open('/etc/unbound/records.json')
# existing_records = json.load(f)
# print(len(existing_records))
# diffs = [val for val in master_dns_records + existing_records \
#     if val not in master_dns_records or val not in existing_records]
# print(diffs)
# print(len(diffs))
# END DEBUG


#
# Load current running DNS entries
#
print('Loading current DNS entries from configmap')
output = shared.run_command(['kubectl', 'get', 'configmap',
                             os.environ['KUBERNETES_UNBOUND_CONFIGMAP_NAME'],
                             '-n', os.environ['KUBERNETES_NAMESPACE'],
                             '-o', 'yaml'])
try:
    # Main data structure used below
    configmap = yaml.load(output, Loader=yaml.FullLoader)
    configmap['metadata'].pop('annotations', None)
    existing_records = json.loads(configmap['data']['records.json'])
except Exception as err:
    raise SystemExit(err)


#
# Any diff between master records and configmap will trigger a reload.
#
print('Comparing new and existing DNS records.')
diffs = [val for val in master_dns_records + existing_records \
    if val not in master_dns_records or val not in existing_records]

if len(diffs) > 0:
    print('    Differences found.  Writing new DNS records to our configmap.')
    records_string = json.dumps(records).replace('"', '\"')
    print("  Records string: '%s'" % records_string)
    configmap['data']['records.json'] = records_string
    with NamedTemporaryFile(mode='w', encoding='utf-8', suffix=".yaml") as tmp:
        yaml.dump(configmap, tmp, default_flow_style=False)
        print("  Applying the configmap")
        shared.run_command(['kubectl', 'replace', '-f', tmp.name])

    print('  Running a rolling restart of the deployment...')
    shared.run_command(['kubectl',
                        '-n', os.environ['KUBERNETES_NAMESPACE'],
                        'rollout', 'restart', 'deployment',
                        os.environ['KUBERNETES_UNBOUND_DEPLOYMENT_NAME']])
else:
    print('    No differences found.  Skipping DNS update')
