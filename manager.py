#!/usr/bin/env python3

import sys
import json
import requests

# TODO - zone file name should come from config
filename = "./zones.conf"
# TODO  - Kea API endpoint should come from K8S
kea_api_endpoint = 'http://cray-dhcp-kea-api:8000'


#
# Query Kea for active server lease information
#
print('Querying Kea in the cluster to find any updated records we need to set')

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
    print('Cannot connect to URL: {}'.format(kea_api_endpoint))
    raise SystemExit(err)
except requests.exceptions.Timeout as err:
    print('Timeout for request: {}'.format(kea_api_endpoint))
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

# It is possible that there are no leases.
if kea_return_code != 0:
    print('Kea HTTP call success, but error in results:')
    print('    Return code: {}'.format(kea_return_code))
    print('    Data       : {}'.format(kea_response_json))
    raise SystemExit()

# Likely some dict comprehension way but can't see it now
lease_entries = [] 
for lease in kea_response_json[0]['arguments']['leases']:
    if not lease['hostname'] or not lease['ip-address']:
        continue
    lease_entries.append({'hostname':lease['hostname'], 'ip-address':lease['ip-address']}) 


#
# Load and parse local DNS config file for current DNS entries
#
print('Loading live DNS entries from local configuration file')

zone_conf_file = open(filename,"r")

# Create a list from the zone file after a bit of cleanup
# All zone entries are managed by this program and will have
# the following original format, parsed and put in a list:
#    local-data: "nid0001 A 10.12.13.1"
#    local-data-ptr: "10.12.13.1 nid0001"
zone_list = [ line.strip().replace(':','').replace('"','').split() \
              for line in zone_conf_file]
zone_conf_file.close()

# Likely some list/dict comprehension thing here I'm not seeing.
dns_entries = []
for line in zone_list:
    # Only A records - PTRs are just 1:1 mirror images.
    if not 'local-data' in line:
        continue
    dns_entries.append({'hostname':line[1], 'ip-address':line[3]})

#
# Match and update zone file entries with Kea DHCP entries
#
print('Comparing values and creating new DNS config file')
# Any proper value in dhcp leases that's not in dns is a diff
# and we will rewrite the config file.
diff = False
for lease in lease_entries:
    found = False
    for entry in dns_entries:
        if lease['hostname'] == entry['hostname'] and \
           lease['ip-address'] == entry['ip-address']:
            found = True
        else:
            continue
    if found is False:
        print('    DNS entry not found {}'.format(lease))
        diff = True
        break

if diff is True:
    print('    Differences found.  Writing DNS file.')
    zone_conf_file = open(filename,"w+")
    for entry in lease_entries:
        print('    New entry:')
        print('      local-data: "{} A {}"'.format(entry['hostname'],entry['ip-address']))
        print('      local-data-ptr: "{} {}"'.format(entry['ip-address'],entry['hostname']))
        zone_conf_file.write('    local-data: "{} A {}"\n'.format(entry['hostname'],entry['ip-address']))
        zone_conf_file.write('    local-data-ptr: "{} {}"\n'.format(entry['ip-address'],entry['hostname']))
    zone_conf_file.close()
else:
    print('    No differences found.  Skipping DNS update')
