#!/usr/bin/env python3
# Copyright 2014-2020 Hewlett Packard Enterprise Development LP

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
def on_error(err, exit=False):
    if exit:
        print('ERROR: {}'.format(err))
        sys.exit(1)
    else:
        print('NOTICE: {}'.format(err))

#
# Remote calls to Kea, SMD and SLS with wrapper for retry and exceptions
#
def remote_request(remote_type ,remote_url, headers=None, data=None, exit_on_error=False):
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
            message = 'remote call to {}: {}'.format(remote_url, err)
            if connection_retries <= max_connection_retries:
                on_error('failed connection attempt in {}'.format(message))
                on_error('    retrying connection shortly...')
                time.sleep(wait_seconds_between_retries)
                continue

            on_error('exception in {}'.format(message))
            if exit_on_error:
                raise SystemExit(err) # Allow the exception to bubble up.
            else:
                remote_response = []
                break

    return remote_response


#
# Perform Kea error checking and and data validation.
#
def get_kea_records(kea_response_json):
    kea_records = None

    # Data check: because of an exception we may have an empty list
    # Create a stub record
    if not kea_response_json:
        kea_response_json.append({'result': None, 'arguments': {'Dhcp4': []}})

    # Check Kea return codes. (Kea codes are 0,1,2,3)
    kea_return_code = kea_response_json[0]['result']
    if kea_return_code != 0:
        on_error('Kea response contains error in results code:')
        on_error('    results code: {}'.format(kea_return_code))
        if not kea_return_code:
            on_error('    exception in call to Kea')
        if kea_return_code == 3:
            on_error('    no leases found in Kea')

    # Make sure that Kea is actually returning data!
    if 'arguments' not in kea_response_json[0] or \
        'Dhcp4' not in kea_response_json[0]['arguments']:
        on_error('Kea API returned successfully, but with no leases.')
        on_error('    return code: {}'.format(kea_return_code))
        on_error('    return data: {}'.format(kea_response_json))
        kea_records = {'result': None, 'arguments': {'Dhcp4': []}}
    else:
        kea_records = kea_response_json[0]['arguments']['Dhcp4']

    return kea_records

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
ts = time.perf_counter()
kea_url = os.environ['KEA_API_ENDPOINT']
# DEBUG
#kea_url = 'http://cray-dhcp-kea-api:8000'
kea_headers = {"Content-Type": "application/json"}
kea_request = {"command": "config-get", "service": ["dhcp4"]}

kea_response_json = remote_request('POST',
                                    kea_url,
                                    headers=kea_headers,
                                    data=kea_request)

# Retrieve cleansed records that are pointing to the correct location
kea_records = get_kea_records(kea_response_json)

# Kea leases or generally canonical as to what should exist in DNS
te = time.perf_counter()
print('Retrieved Kea data ({0:.5}s)'.format(te-ts))


# Global lease check - non-fatal in v1.4
kea_global_leases = []
if 'reservations' not in kea_records:
    on_error('Kea global reservations data is empty')
else:
    kea_global_leases = kea_records['reservations']
    print('Found {} leases and reservations in Kea globals'.format(len(kea_global_leases)))


#
# Load per-subnet leases/reservations - can be also be global.
# Prefer local beginning with v1.4. Data cleanup and adding in globals for now.
#
ts = time.perf_counter()
kea_local_leases = []
kea_subnets = []
if not 'subnet4' in kea_records:
    on_error('Kea Dhcp4 lease and reservation data is empty')
else:
    kea_subnets = kea_records['subnet4']
    print('Found {} subnets in Kea'.format(len(kea_subnets)))

for subnet in kea_subnets:
    if 'reservations' not in subnet:
        continue
    for lease in subnet['reservations']:
        record = { 'hostname': lease['hostname'],
                   'ip-address': lease['ip-address'] }
        kea_local_leases.append(record)

te = time.perf_counter()
print('Found {0} leases and reservations in Kea local subnets ({1:.5f}s)'.format(len(kea_local_leases),te-ts))


#
# Merge global and local Kea leases/reservations - with cleanup.
#
ts = time.perf_counter()
for lease in kea_local_leases + kea_global_leases:
    # Some nodes might be in discovery
    if 'hostname' not in lease or 'ip-address' not in lease:
        continue

    # Having empty values is an error
    if not lease['hostname'].strip() or not lease['ip-address'].strip():
        on_error('Kea returned lease with incomplete data, continuing {}'.format(lease))
        continue

    # CASMNET-124: change nid to nid-nmn for v1.3 because nid is HSN
    #   TODO - move this to Central DNS after data naming cleanup
    record = None
    if lease['hostname'].find('nid') > -1:
        record = { 'hostname': lease['hostname'] + '-nmn',
                   'ip-address': lease['ip-address'] }
    else:
        record = { 'hostname': lease['hostname'],
                   'ip-address': lease['ip-address'] }

    if record not in master_dns_records:
        master_dns_records.append(record)

te = time.perf_counter()
print('Gathered {0} total leases and reservations local and global ({1:.5f}s)'.format(len(master_dns_records),te-ts))


#
# CASMNET-121: Query SMD for CNAME/alias information
#   TODO - move this to Central DNS
#
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
ts = time.perf_counter()
smd_request = 'http://cray-smd/hsm/v1/Inventory/EthernetInterfaces'
smd_records = remote_request('GET', smd_request)
te = time.perf_counter()
print('Queried SMD to find any xname records we need to set ({0:.5f}s)'.format(te-ts))
print('Found {} records in SMD'.format(len(smd_records)))


#
# Find CNAME records in SMD
#
ts = time.perf_counter()
new_records = []
for dns in master_dns_records:
    # Not all records in SMD are desired, only those with matching
    # IP addresses and different hostnames - resulting in CNAMES.
    for smd in smd_records:
        # Skip records without data
        if 'IPAddress' not in smd or 'ComponentID' not in smd:
            continue

        # Skip records with blank data
        if not smd['IPAddress'].strip() or not smd['ComponentID'].strip():
            continue

        # Skip records with same hostname (expected SMD/Kea duplicates)
        if smd['ComponentID'] == dns['hostname']:
            break

        if smd['IPAddress'] == dns['ip-address']:
            new_record = {'hostname': smd['ComponentID'], 'ip-address': smd['IPAddress']}
            old_record = {'hostname': dns['hostname'], 'ip-address': dns['ip-address']}
            #print('    New CNAME {}'.format(new_record))
            #print('     A record {}'.format(old_record))
            new_records.append(new_record)
            break


#
# Merge SMD xnames/CNAMES with DNS nid-names.  Kea is generally is SoR
#
master_dns_records.extend(new_records)
te = time.perf_counter()
print('Merged new SMD xnames into DNS data structure ({0:.5f}s)'.format(te-ts))


#
# CASMNET-130 and CASMNET-137: UANs and Management NCNs need to have 
#   <hostname>-mgmt entry to the hardware management network and
#   <hostname>-nmn for the node management network.
#   the 
#   TODO - move this to Central DNS expanding use for all Role/SubRole Aliases
#
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
ts = time.perf_counter()
sls_request = 'http://cray-sls/v1/hardware'
sls_records = remote_request('GET', sls_request)


#
# Find UAN and Manager/Worker CNAME records in SLS.
# NOTE:  This is the one place where we are NOT using Kea as SoR because
#        NCNs currently are NOT dynamic/DHCP.
#
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

        for smd in smd_records:
            # Skip records with blank entries
            if not smd['ComponentID'].strip() or not smd['IPAddress'].strip():
                continue

            # Get the HMN IP address
            if smd['ComponentID'] == hmn_xname:
                for alias in sls['ExtraProperties']['Aliases']:
                    mgmt_alias = alias + '-mgmt'
                    new_record = {'hostname': mgmt_alias, 'ip-address': smd['IPAddress']}
                    old_record = {'hostname': hmn_xname, 'ip-address': smd['IPAddress']}
                    #print('    New CNAME {}'.format(new_record))
                    #print('     A record {}'.format(old_record))
                    new_records.append(new_record)

            # Get the NMN IP address
            if smd['ComponentID'] == nmn_xname:
                for alias in sls['ExtraProperties']['Aliases']:
                    nmn_alias = alias + '-nmn'
                    new_record = {'hostname': nmn_alias, 'ip-address': smd['IPAddress']}
                    old_record = {'hostname': nmn_xname, 'ip-address': smd['IPAddress']}
                    #print('    New CNAME {}'.format(new_record))
                    #print('     A record {}'.format(old_record))
                    new_records.append(new_record)

te = time.perf_counter()
print('Queried SLS to find Management and Application records ({0:.5f})'.format(te-ts))
print('Found {} SLS Hardware records.'.format(len(sls_records)))


#
# Merge SLS CNAMES with DNS records.
# This is the one place Kea is not SoR.
#
master_dns_records.extend(new_records)
print('Merged new SLS Application and Management names into DNS data structure')


#
# v1.4+:  Retrieve network structures
#
ts = time.perf_counter()
sls_request = 'http://cray-sls/v1/networks'
sls_networks = remote_request('GET', sls_request)
te = time.perf_counter()
print('Queried SLS to find Network records ({0:.5f})'.format(te-ts))
print('Found {} SLS Network records.'.format(len(sls_networks)))


#
# v1.4+: Get static A record values from network structures
#        TODO:  when moving this to central DNS make some of these
#        proper CNAMES
#
ts = time.perf_counter()
static_records = []
for network in sls_networks:
    if not 'ExtraProperties' in network:
        continue

    if not 'Subnets' in network['ExtraProperties'] or \
       not network['ExtraProperties']['Subnets']:
        continue

    subnets = network['ExtraProperties']['Subnets']
    for subnet in subnets:
        if not 'IPReservations' in subnet:
            continue

        subdomain = network['Name'].lower()
        reservations = subnet['IPReservations']
        for reservation in reservations:
            if 'Name' in reservation and reservation['Name'].strip():
                # TODO: split this out as A Record in central DNS.
                # NOTE: append subdomain to A Record to enforce part of DNS hierarchy.
                record = { 'hostname': '{}.{}'.format(reservation['Name'],subdomain),   
                           'ip-address': reservation['IPAddress'] }
                static_records.append(record)

                # CASMNET-379 - default no subdomain requests to NMN.  This needs to
                # be removed when the full domain hierarchy is put into place.
                if subdomain == 'nmn':
                    record = { 'hostname': '{}'.format(reservation['Name']),   
                               'ip-address': reservation['IPAddress'] }
                    static_records.append(record)
            if 'Aliases' in reservation: 
                for alias in reservation['Aliases']:
                    # TODO: split this out as a CNAME in central DNS.
                    if not alias:
                        continue
                    record = { 'hostname': alias, 'ip-address': reservation['IPAddress'] }
                    static_records.append(record)

te = time.perf_counter()
master_dns_records.extend(static_records)
print('Merged new static and alias SLS entries into DNS data structure ({0:.5f}s)'.format(te-ts))


#
# Load current running DNS entries
#
ts = time.perf_counter()
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
# DEBUG
#f = open('/etc/unbound/records.json')
#existing_records = json.load(f)
te = time.perf_counter()
print('Loaded current DNS entries from configmap ({0:.5}s)'.format(te-ts))


#
# Any diff between master records and configmap will trigger a reload.
#
print('Number of existing records {}'.format(len(existing_records)))
print('Number of new records (including duplicates) {}'.format(len(master_dns_records)))
ts = time.perf_counter()
diffs = [
            val for val in master_dns_records + existing_records
            if val not in master_dns_records or val not in existing_records
        ]
te = time.perf_counter()
print('Comparing new and existing DNS records ({0:.5f})'.format(te-ts))

if len(diffs) > 0:
    ts = time.perf_counter()
    print('    Differences found.  Writing new DNS records to our configmap.')
    records_string = json.dumps(master_dns_records).replace('"', '\"')
    configmap['data']['records.json'] = records_string
    with NamedTemporaryFile(mode='w', encoding='utf-8', suffix=".yaml") as tmp:
        yaml.dump(configmap, tmp, default_flow_style=False)
        print("  Applying the configmap")
        shared.run_command(['kubectl', 'replace', '--force', '-f', tmp.name])

    print('  Running a rolling restart of the deployment...')
    shared.run_command(['kubectl',
                        '-n', os.environ['KUBERNETES_NAMESPACE'],
                        'rollout', 'restart', 'deployment',
                        os.environ['KUBERNETES_UNBOUND_DEPLOYMENT_NAME']])
    te = time.perf_counter()
    print('Merged records and reloaded configmap ({0:.5f}s)'.format(te-ts))
else:
    print('    No differences found.  Skipping DNS update')
