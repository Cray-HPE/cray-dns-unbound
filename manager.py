#!/usr/bin/env python3

import os
import sys
import json
import requests
import time
import shared

#
# Query Kea for active server lease information
#
time.sleep(3) # a really quick sleep upfront as it'll give our istio-proxy channel out to be ready
              # better chance for a successful first attempt connecting to Kea through the mesh
print('Querying Kea in the cluster to find any updated records we need to set')

kea_headers = {"Content-Type": "application/json"}
kea_request = {"command": "lease4-get-all", "service": ["dhcp4"]}

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

kea_response_json = kea_response.json()
kea_return_code = kea_response_json[0]['result']

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

#
# Load and parse local DNS config file for current DNS entries
#
print('Loading current DNS entries from configmap')
output = shared.run_command(['kubectl', 'get', 'configmap', os.environ['KUBERNETES_UNBOUND_CONFIGMAP_NAME'], '-n',
    os.environ['KUBERNETES_NAMESPACE'], '-o', 'jsonpath={.data[\'records\\.json\']}'])
try:
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
for lease in kea_response_json[0]['arguments']['leases']:
    if not lease['hostname'] or not lease['ip-address']:
        # ignore any Kea lease that doesn't have both a hostname and IP
        continue
    create_new = True
    for record in records:
        if lease['hostname'] == record['hostname']:
            create_new = False
            if lease['ip-address'] != record['ip-address']:
                record['ip-address'] = lease['ip-address']
                diff = True
                print('    Existing hostname DNS record to update {}'.format(lease))
            break
    if create_new:
        records.append({'hostname': lease['hostname'], 'ip-address': lease['ip-address']})
        diff = True
        print('    New hostname DNS record to add {}'.format(lease))

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
