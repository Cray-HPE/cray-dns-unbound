#!/usr/bin/env python3

import sys
import json
import requests


#
# Query Kea for active server lease information
#
print('Querying Kea in the cluster to find any updated records we need to set')
# TODO  - Kea API endpoint should come from K8S
kea_api_endpoint = 'http://cray-dhcp-kea-api:8000'
kea_headers = {"Content-Type": "application/json"}
kea_request = {"command": "lease4-get-all", "service": [ "dhcp4" ] }

try:
    # Convert explicitly to json to catch errors up front.
    kea_request_json = json.dumps(kea_request)

    # Call Kea to retrieve active kea_response
    kea_response = requests.post(url = kea_api_endpoint, \
                           headers = kea_headers, \
                           data = kea_request_json)
    kea_response.raise_for_status()

    kea_response_json = kea_response.json()
except requests.exceptions.ConnectionError as err:
    print('Cannot connect to URL: {}'.format(url))
    raise SystemExit(err)
except requests.exceptions.Timeout as err:
    print('Timeout for request: {}'.format(url))
    raise SystemExit(err)
except requests.exceptions.RequestException as err:
    print('Error occurred in kea response from: {}'.format(kea_response.url))
    print('    HTTP error code: {}'.format(kea_response.status_code))
    print('    HTTP response  : {}'.format(kea_response.text))
    raise SystemExit(err)
except Exception as err:
    raise SystemExit(err)

kea_response_json = kea_response.json()
kea_return_code = kea_response_json[0]['result']

if kea_return_code != 0:
    print('Kea HTTP call success, but error in results:')
    print('    Return code: {}'.format(kea_return_code))
    print('    Data       : {}'.format(kea_response_json))
    raise SystemExit()

kea_leases = kea_response_json[0]['arguments']['leases']
for lease in leases:
    print(lease)


#
# Load and parse local DNS config file for current DNS entries
#
print('Loading live DNS entries from local configuration file')