#!/usr/bin/env python3
# Copyright 2014-2022 Hewlett Packard Enterprise Development LP

import os
import re
import sys
import gzip
import json
import yaml
import time
import codecs
import shared
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import subprocess
from urllib.parse import urljoin
import logging
from tempfile import NamedTemporaryFile

# globals
log = logging.getLogger(__name__)
log.setLevel(level = os.environ['LOG_LEVEL'])

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
log.addHandler(handler)

class APIRequest(object):
    """

    Example use:
        api_request = APIRequest('http://api.com')
        response = api_request('GET', '/get/stuff')

        print (f"response.status_code")
        print (f"{response.status_code}")
        print()
        print (f"response.reason")
        print (f"{response.reason}")
        print()
        print (f"response.text")
        print (f"{response.text}")
        print()
        print (f"response.json")
        print (f"{response.json()}")
    """

    def __init__(self, base_url, headers=None):
        if not base_url.endswith('/'):
            base_url += '/'
        self._base_url = base_url

        if headers is not None:
            self._headers = headers
        else:
            self._headers = {}

    def __call__(self, method, route, **kwargs):

        if route.startswith('/'):
            route = route[1:]

        url = urljoin(self._base_url, route, allow_fragments=False)

        headers = kwargs.pop('headers', {})
        headers.update(self._headers)

        retry_strategy = Retry(
            total=10,
            backoff_factor=0.1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["PATCH", "DELETE", "POST","HEAD", "GET", "OPTIONS"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        http = requests.Session()
        http.mount("https://", adapter)
        http.mount("http://", adapter)

        response = http.request(method=method, url=url, headers=headers, **kwargs)

        if 'data' in kwargs:
            log.debug(f"{method} {url} with headers:"
                     f"{json.dumps(headers, indent=4)}"
                     f"and data:"
                     f"{json.dumps(kwargs['data'], indent=4)}")
        elif 'json' in kwargs:
            log.debug(f"{method} {url} with headers:"
                     f"{json.dumps(headers, indent=4)}"
                     f"and JSON:"
                     f"{json.dumps(kwargs['json'], indent=4)}")
        else:
            log.debug(f"{method} {url} with headers:"
                     f"{json.dumps(headers, indent=4)}")
        log.debug(f"Response to {method} {url} => {response.status_code} {response.reason}"
                 f"{response.text}")

        return response

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
        log.error(f'Kea response contains error in results code:')
        log.error(f'    results code: {kea_return_code}')
        if not kea_return_code:
            log.error(f'    exception in call to Kea')
        if kea_return_code == 3:
            log.error(f'    no leases found in Kea')

    # Make sure that Kea is actually returning data!
    if 'arguments' not in kea_response_json[0] or \
            'Dhcp4' not in kea_response_json[0]['arguments']:
        log.error(f'Kea API returned successfully, but with no leases.')
        log.error(f'    return code: {kea_return_code}')
        log.error(f'    return data: {kea_response_json}')
        kea_records = {'result': None, 'arguments': {'Dhcp4': []}}
    else:
        kea_records = kea_response_json[0]['arguments']['Dhcp4']

    return kea_records

def main():
    #
    # Give istio-proxy channel a chance to be ready
    #
    time.sleep(3)

    #
    # concurrency check
    #
    # ts = time.perf_counter()

    api_errors = False

    # setup api urls
    kea_api = APIRequest(os.environ['KEA_API_ENDPOINT'])
    smd_api = APIRequest(os.environ['SMD_API_ENDPOINT'])
    sls_api = APIRequest(os.environ['SLS_API_ENDPOINT'])

    # Setup HSN NIC used for nid alias
    #
    # Previous CSM versions associate all HSN NIC IPs with the nid alias
    #
    # ncn-m001:~ # host nid001046
    # nid001046 has address 10.150.0.45
    # nid001046 has address 10.150.0.126
    # nid001046 has address 10.150.0.142
    # nid001046 has address 10.150.0.141
    #
    # Some WLMs don't handle this well so only associate the alias with a
    # single NIC unless the HSN_NIC_ALIAS environment variable isn't set or
    # is set incorrectly in which case default to the old behaviour.
    try:
        nic_index = os.environ['HSN_NIC_ALIAS']
        if str(nic_index).isnumeric():
            nic_index = 'h' + str(nic_index)
            log.info(f'Using interface ' + nic_index + f' to build the nid alias')
        elif nic_index == 'all':
            log.info(f'Using all interfaces to build the nid alias')
        else:
            log.error(f'HSN_NIC_ALIAS is not numeric or all, defaulting to all nics for alias')
            nic_index = 'all'
    except KeyError:
        log.error(f'HSN_NIC_ALIAS environment variable not set, defaulting to all nics for alias')
        nic_index = 'all'

    #
    # Master data structure for DNS records which *must* exist
    #
    master_dns_records = []

    #
    # Query Kea for active server lease information
    #
    log.info(f'Querying Kea in the cluster to find any updated records we need to set')
    ts = time.perf_counter()
    kea_headers = {"Content-Type": "application/json"}
    kea_request = {"command": "config-get", "service": ["dhcp4"]}

    resp = kea_api('POST', '/', headers=kea_headers, json=kea_request)
    kea_response_json = resp.json()
    if len(kea_response_json) == 0:
        log.warning(f'Did not get any data from Kea API call')
        api_errors = True

    # Retrieve cleansed records that are pointing to the correct location
    kea_records = get_kea_records(kea_response_json)

    # Kea leases or generally canonical as to what should exist in DNS
    te = time.perf_counter()
    log.info(f'Retrieved Kea data {int(te - ts)}s')

    # Global lease check - non-fatal in v1.4
    kea_global_leases = []
    if 'reservations' not in kea_records:
        log.error(f'Kea global reservations data is empty')
    else:
        kea_global_leases = kea_records['reservations']
        log.info(f'Found {len(kea_global_leases)} leases and reservations in Kea globals')

    #
    # Load per-subnet leases/reservations - can be also be global.
    # Prefer local beginning with v1.4. Data cleanup and adding in globals for now.
    #
    ts = time.perf_counter()
    kea_local_leases = []
    kea_subnets = []
    if not 'subnet4' in kea_records:
        log.error(f'Kea Dhcp4 lease and reservation data is empty')
    else:
        kea_subnets = kea_records['subnet4']
        log.info(f'Found {len(kea_subnets)} subnets in Kea')

    for subnet in kea_subnets:
        if 'reservations' not in subnet:
            continue
        for lease in subnet['reservations']:
            record = {'hostname': lease['hostname'],
                      'ip-address': lease['ip-address']}
            kea_local_leases.append(record)

    te = time.perf_counter()
    log.info(f'Found {len(kea_local_leases)} leases and reservations in Kea local subnets {int(te - ts)}s')

    # Merge global and local Kea leases/reservations - with cleanup.
    #
    ts = time.perf_counter()
    for lease in kea_local_leases + kea_global_leases:
        # Some nodes might be in discovery
        if 'hostname' not in lease or 'ip-address' not in lease:
            continue

        # Having empty values is an error
        if not lease['hostname'].strip() or not lease['ip-address'].strip():
            log.error('Kea returned lease with incomplete data, continuing {lease}')
            continue

        # CASMNET-124: change nid to nid-nmn for v1.3 because nid is HSN
        #   TODO - move this to Central DNS after data naming cleanup
        record = None
        if lease['hostname'].find('nid') > -1:
            record = {'hostname': lease['hostname'] + '-nmn',
                      'ip-address': lease['ip-address']}
        else:
            record = {'hostname': lease['hostname'],
                      'ip-address': lease['ip-address']}

        if record not in master_dns_records:
            master_dns_records.append(record)

    te = time.perf_counter()
    log.info(f'Gathered {len(master_dns_records)} total leases and reservations local and global {int(te - ts)}s')


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
    resp = smd_api('GET', '/hsm/v2/Inventory/EthernetInterfaces')
    smd_records = resp.json()

    resp = smd_api('GET', '/hsm/v2/State/Components/')
    smd_state_components = resp.json()

    if len(smd_records) == 0:
        log.warning(f'Did not get any data from SMD EthernetInterfaces API call')
        api_errors = True

    te = time.perf_counter()
    log.info(f'Queried SMD to find any xname records we need to set {int(te - ts)}s')
    log.info(f'Found {len(smd_records)} records in SMD')

    #
    # Find CNAME records in SMD
    #
    ts = time.perf_counter()
    new_records = []
    for dns in master_dns_records:
        # Not all records in SMD are desired, only those with matching
        # IP addresses and different hostnames - resulting in CNAMES.
        for smd in smd_records:
            # Skip records with blank data
            if smd['IPAddresses'] == [] or not smd['ComponentID'].strip() or \
                    smd['IPAddresses'][0]['IPAddress'] == '':
                continue

            # Skip records with same hostname (expected SMD/Kea duplicates)
            if smd['ComponentID'] == dns['hostname']:
                break

            if smd['IPAddresses'][0]['IPAddress'] == dns['ip-address']:
                new_record = {'hostname': smd['ComponentID'], 'ip-address': smd[
                    'IPAddresses'][0]['IPAddress']}
                old_record = {'hostname': dns['hostname'], 'ip-address': dns['ip-address']}
                # print('    New CNAME {}'.format(new_record))
                # print('     A record {}'.format(old_record))
                new_records.append(new_record)
                break

    #
    # Merge SMD xnames/CNAMES with DNS nid-names.  Kea is generally is SoR
    #
    master_dns_records.extend(new_records)
    te = time.perf_counter()
    log.info(f'Merged new SMD xnames into DNS data structure {int(te - ts)}s')

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
    resp = sls_api('GET','/v1/hardware')
    sls_records = resp.json()

    if len(sls_records) == 0:
        log.warning(f'Did not get any data from SLS hardware API call')
        api_errors = True

    #
    # 1. CASMINST-1114 PART1: Find nid names that are in kea and associate with their xname.
    # 2. Find UAN and Manager/Worker CNAME records in SLS.
    # NOTE:  This is the one place where we are NOT using Kea as SoR because
    #        NCNs currently are NOT dynamic/DHCP.
    #
    nid_records = []
    new_records = []
    # Not all records in SLS are desired, only those with xnames
    # where the SubRole is UAN.
    for sls in sls_records:
        # Skip records without minimal required data
        if 'ExtraProperties' not in sls or \
                'Role' not in sls['ExtraProperties'] or \
                'Aliases' not in sls['ExtraProperties']:
            continue

        # check for UAN artficial NID number
        # smd_state_components data is tied to discovery data
        # the data will be dynamic and reason for extra logic for error handling
        if sls['ExtraProperties']['Role'] == 'Application':
            xname = sls['Xname']
            nidname = ''
            for record in smd_state_components['Components']:
                if record['ID'] == xname:
                    if 'NID' in record:
                        nidname = 'nid' + str(record['NID'])
            if nidname != '':
                nid_records.append({'nidname': nidname, 'xname': xname})

        # get NCN nid number
        if sls['ExtraProperties']['Role'] == 'Management':
            nidname = 'nid' + str(sls['ExtraProperties']['NID'])
            xname = sls['Xname']
            nid_records.append({'nidname': nidname, 'xname': xname})

        # Assemble nid name / xname correlation for HSN records later
        # TODO: move this correlation around in Central DNS
        for dns in master_dns_records:
            if dns['hostname'].find('nid') > -1:
                if dns['hostname'].replace('-nmn', '') not in sls['ExtraProperties']['Aliases']:
                    continue
                nidname = dns['hostname'].replace('-nmn', '')
                xname = sls['Xname']
                nid_records.append({'nidname': nidname, 'xname': xname})

        if sls['ExtraProperties']['Role'] == 'Management' or \
                sls['ExtraProperties']['Role'] == 'Application':

            hmn_xname = sls['Parent']
            nmn_xname = sls['Xname']

            for smd in smd_records:
                # Skip records with blank entries
                if not smd['ComponentID'].strip() or smd['IPAddresses'] == [] or \
                        smd['IPAddresses'][0]['IPAddress'] == '':
                    continue

                # Get the HMN IP address
                if smd['ComponentID'] == hmn_xname:
                    for alias in sls['ExtraProperties']['Aliases']:
                        mgmt_alias = alias + '-mgmt'
                        new_record = {'hostname': mgmt_alias, 'ip-address': smd[
                            'IPAddresses'][0]['IPAddress']}
                        old_record = {'hostname': hmn_xname, 'ip-address': smd[
                            'IPAddresses'][0]['IPAddress']}
                        new_records.append(new_record)

                # Get the NMN IP address
                if smd['ComponentID'] == nmn_xname:
                    # create records for all aliases for node in NMN
                    for alias in sls['ExtraProperties']['Aliases']:
                        # get alias and create record
                        record = {'hostname': alias, 'ip-address': smd[
                            'IPAddresses'][0]['IPAddress']}
                        new_records.append(record)
                        # add -nmn to alias and create record
                        nmn_alias = alias + '-nmn'
                        nmn_alias_record = {'hostname': nmn_alias, 'ip-address': smd[
                            'IPAddresses'][0]['IPAddress']}
                        new_records.append(nmn_alias_record)

    te = time.perf_counter()
    log.info(f'Queried SLS to find Management, Application and HSN nid records {int(te - ts)}')
    log.info(f'Found {len(sls_records)} SLS Hardware records.')
    #
    # Merge SLS CNAMES with DNS records.
    # This is the one place Kea is not SoR.
    #
    master_dns_records.extend(new_records)
    log.info(f'Merged new SLS Application and Management names into DNS data structure')

    #
    # v1.4+:  Retrieve network structures
    #
    ts = time.perf_counter()
    resp = sls_api('GET', '/v1/networks')
    sls_networks = resp.json()

    if len(sls_networks) == 0:
        log.warning(f'Did not get any data from SLS network API call')
        api_errors = True

    te = time.perf_counter()
    log.info(f'Queried SLS to find Network records {int(te - ts)}')
    log.info(f'Found {len(sls_networks)} SLS Network records.')

    #
    # v1.4+: Get static A record values from network structures
    #        TODO:  when moving this to central DNS make some of these
    #        proper CNAMES
    #
    ts = time.perf_counter()
    hsn_matches = 0
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

            subdomain = re.sub(r'^(NMN|HMN|HSN|MTL|CAN|CHN|CMN)_.*$', r'\1', network['Name']).lower()
            reservations = subnet['IPReservations']
            for reservation in reservations:
                if 'Name' in reservation and reservation['Name'].strip():
                    # TODO: split this out as A Record in central DNS.
                    # NOTE: APPEND SUBDOMAIN to A Record to enforce part of DNS hierarchy.
                    record = {'hostname': '{}.{}'.format(reservation['Name'], subdomain),
                              'ip-address': reservation['IPAddress']}
                    static_records.append(record)

                    # CASMNET-379 - default no subdomain requests to NMN.  This needs to
                    # be removed when the full domain hierarchy is put into place.
                    if subdomain == 'nmn':
                        record = {'hostname': '{}'.format(reservation['Name']),
                                  'ip-address': reservation['IPAddress']}
                        static_records.append(record)
                if 'Aliases' in reservation:
                    for alias in reservation['Aliases']:
                        # TODO: split this out as a CNAME in central DNS.
                        if not alias:
                            continue
                        record = {'hostname': alias, 'ip-address': reservation['IPAddress']}
                        static_records.append(record)

                # CASMINST-1114 PART 2: nid aliases for HSN xname records.
                # TODO: This needs to be done differently in central DNS.
                # Three records per: nid002023 x1003c7s7b1n1h0 nid002023-hsn0
                # Operate only on xnames
                if reservation['Name'][0] == 'x':
                    reservation_xname = re.sub(r'h\d+$', '', reservation['Name'])  # remove port
                    reservation_xname = re.sub(r'([a-z])0+([0-9]+[a-z])', r'\1\2', reservation_xname)  # zero padding
                    for nid in nid_records:
                        if nid['xname'] == reservation_xname:
                            hsn_matches += 1

                            if subdomain != 'chn':

                                ipv4 = reservation['IPAddress']

                                if nic_index in reservation['Name'] or nic_index == 'all':
                                    record = {'hostname': nid['nidname'], 'ip-address': ipv4}
                                    static_records.append(record)

                                port = re.sub(r'^(.*)h(\d+)$', r'\2', reservation['Name'])
                                record = {'hostname': nid['nidname'] + '-hsn' + port, 'ip-address': ipv4}
                                static_records.append(record)

                                record = {'hostname': reservation['Name'], 'ip-address': ipv4}
                                static_records.append(record)

    te = time.perf_counter()
    master_dns_records.extend(static_records)
    log.info(f'Merged new static and alias SLS entries into DNS data structure {int(te - ts)}')

    log.info(f'Found {len(nid_records)} compute node nid definitions in SLS hardware.')
    log.info(f'Matched {hsn_matches} compute node nid definitions in SLS network reservations.')

    #
    # Load current running DNS entries
    #
    ts = time.perf_counter()
    log.info(f'Running kubectl to retrieve existing records and configuration.')
    output = shared.run_command(['kubectl', 'get', 'configmap',
                                 os.environ['KUBERNETES_UNBOUND_CONFIGMAP_NAME'],
                                 '-n', os.environ['KUBERNETES_NAMESPACE'],
                                 '-o', 'yaml'])
    try:
        # Main data structure used below
        configmap = yaml.load(output, Loader=yaml.FullLoader)
        configmap['metadata'].pop('annotations', None)

        # Read in base64 encoded and gzip'd records
        try:
            configmap_records = configmap['binaryData']['records.json.gz']  # String
        except KeyError as key:
            # If the binaryData."records.json.gz" key is missing from the ConfigMap then set it to the
            # base64 encoded, gzipped representation of [] to ensure there is a blank set of records to
            # use for comparison forcing manager.py to add all the records it generated to the configmap.
            log.error(f'Key {key} missing from ConfigMap. Setting to [] to force rebuild of records.')
            configmap['binaryData'] = {"records.json.gz": "H4sICLQ/Z2AAA3JlY29yZHMuanNvbgCLjuUCAETSaHADAAAA"}
            configmap_records = configmap['binaryData']['records.json.gz']  # String

        configmap_records = codecs.encode(configmap_records, encoding='utf-8')  # Bytes object
        configmap_records = codecs.decode(configmap_records, encoding='base64')
        configmap_records = gzip.decompress(configmap_records)
        existing_records = json.loads(configmap_records)
    except Exception as err:
        raise SystemExit(err)
    # DEBUG
    # f = gzip.open('/etc/unbound/records.json.gz')
    # existing_records = json.load(f)
    te = time.perf_counter()
    log.info(f'Loaded current DNS entries from configmap {int(te - ts)}')

    #
    # Any diff between master records and configmap will trigger a reload.
    #
    log.info(f'Number of existing records {len(existing_records)}')
    log.info(f'Number of new records (including duplicates) {len(master_dns_records)}')
    ts = time.perf_counter()

    diffs = False
    if len(existing_records) != len(master_dns_records):
        diffs = True
    else:
        master_dns_records.sort(key=lambda r: r['hostname'])
        if master_dns_records != existing_records:
            diffs = True

    te = time.perf_counter()
    log.info(f'Comparing new and existing DNS records {int(te - ts)}')

    if not api_errors and diffs:
        ts = time.perf_counter()
        log.info(f'    Differences found.  Writing new DNS records to our configmap.')
        records_string = json.dumps(master_dns_records).replace('"', '\"')  # String
        records_string = codecs.encode(records_string, encoding='utf-8')  # Bytes object
        records_string = gzip.compress(records_string)
        records_string = codecs.encode(records_string, encoding='base64')
        configmap['binaryData']['records.json.gz'] = records_string
        with NamedTemporaryFile(mode='w', encoding='utf-8', suffix=".yaml") as tmp:
            yaml.dump(configmap, tmp, default_flow_style=False)
            try:
                log.info(f'  Applying the configmap')
                shared.run_command(['kubectl', 'replace', '--force', '-f', tmp.name])
            except SystemExit:
                log.error(f'  Failed to apply the configmap, retrying.')
                shared.run_command(['kubectl', 'replace', '--force', '-f', tmp.name])

        te = time.perf_counter()
        log.info(f'Merged records and reloaded configmap {int(te - ts)}')

    elif api_errors and len(master_dns_records) > len(existing_records):
        ts = time.perf_counter()
        log.info(f'    Differences found.  Writing new DNS records to our configmap.')
        log.info(f'    API errors occured but generated more records than previous created.')
        records_string = json.dumps(master_dns_records).replace('"', '\"')  # String
        records_string = codecs.encode(records_string, encoding='utf-8')  # Bytes object
        records_string = gzip.compress(records_string)
        records_string = codecs.encode(records_string, encoding='base64')
        configmap['binaryData']['records.json.gz'] = records_string
        with NamedTemporaryFile(mode='w', encoding='utf-8', suffix=".yaml") as tmp:
            yaml.dump(configmap, tmp, default_flow_style=False)
            try:
                log.info(f'  Applying the configmap')
                shared.run_command(['kubectl', 'replace', '--force', '-f', tmp.name])
            except SystemExit:
                log.error(f'  Failed to apply the configmap, retrying.')
                shared.run_command(['kubectl', 'replace', '--force', '-f', tmp.name])

        te = time.perf_counter()
        log.info(f'Merged records and reloaded configmap {int(te - ts)}s)')
    elif api_errors and len(master_dns_records) < len(existing_records):
        ts = time.perf_counter()
        log.info(f'    Differences found.  NOT writing DNS records to configmap.')
        log.info(f'    API errors and generated record was less than previous list')
        te = time.perf_counter()
        log.info(f'NO CHANGES to unbound configmap {int(te - ts)}')
    else:
        log.info(f'    No differences found.  Skipping DNS update')
if __name__ == "__main__":
    main()
