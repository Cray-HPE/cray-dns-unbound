#!/usr/bin/env python3

import sys
import json
import requests

if len(sys.argv) != 2:
    print('Usage: {} <add|del>'.format(sys.argv[0]))
    sys.exit(1)

call_type = None
if sys.argv[1] == 'add':
    call_type = "lease4-add"
elif sys.argv[1] == 'del':
    call_type = "lease4-del"
else:
    print('Usage: {} <add|del>'.format(sys.argv[0]))


# 10.254.2 = HMN
# 10.254.4 = NMN
subnet = '10.254.2'

kea_api_endpoint = 'http://cray-dhcp-kea-api:8000'
kea_headers = {'Content-Type': 'application/json'}

kea_request = {"command": "lease4-del",
               "service": [ "dhcp4" ],
               "arguments": {"hw-address": "a4:bf:01:3e:ef:xx",
                             "hostname": "nid0000xx",
                             "ip-address": "10.254.2.xx",
                             "force-create": True }
              }

kea_request['command'] = call_type

for num in range(50,55):
    mac_address = 'de:ad:be:ef:ff:{:02x}'.format(num)
    ip_address = '{}.{:d}'.format(subnet,num)
    host_name = 'nid000{:03d}'.format(num)

    kea_request['arguments']['hw-address'] = mac_address
    kea_request['arguments']['hostname'] = host_name
    kea_request['arguments']['ip-address'] = ip_address

    try:
        print('{}: hostname={} ip={} mac={}'.format(call_type,host_name,ip_address,mac_address))
        kea_request_json = json.dumps(kea_request)
        r = requests.post(url=kea_api_endpoint, \
                               headers=kea_headers, \
                               data=kea_request_json)
        r.raise_for_status()
    except requests.exceptions.ConnectionError as err:
        print('Cannot connect to URL: {}'.format(url))
        raise SystemExit(err)
    except requests.exceptions.Timeout as err:
        print('Timeout for request: {}'.format(url))
        raise SystemExit(err)
    except requests.exceptions.RequestException as err:
        print('Error occurred seeding leases from: {}'.format(r.url))
        print('    HTTP error code: {}'.format(r.status_code))
        print('    HTTP response  : {}'.format(r.text))
        raise SystemExit(err)
    except Exception as err:
        raise SystemExit(err)

        
    print(r.text)
    print(r.json())
