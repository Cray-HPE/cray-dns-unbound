#!/usr/bin/env python3

import os
import requests
import shared
import re
import time

time.sleep(3) # a really quick sleep upfront as it'll give our istio-proxy channel out to be ready
              # better chance for a successful first attempt connecting out through the mesh

print('Loading current CoreDNS configmap in namespace {}: {}'.format(os.environ['KUBERNETES_COREDNS_NAMESPACE'], os.environ['KUBERNETES_COREDNS_CONFIGMAP_NAME']))
# we'll give some time for connection errors to settle, as this job will work within the
# istio service mesh, and connectivity out through the istio-proxy out may take just
# a few. We'll give it about 30 seconds before we fail hard for the job
connection_retries = 0
max_connection_retries = 10
wait_seconds_between_retries = 3
while True:
    try:
        corefile = shared.run_command(['kubectl', 'get', 'configmap', os.environ['KUBERNETES_COREDNS_CONFIGMAP_NAME'], '-n',
            os.environ['KUBERNETES_COREDNS_NAMESPACE'], '-o', 'jsonpath={.data[\'Corefile\']}'])
        break
    except BaseException as err:
        connection_retries += 1
        message = 'Error connecting to Kubernetes API: {}'.format(err)
        if connection_retries <= max_connection_retries:
            print('Retrying connection shortly...')
            time.sleep(wait_seconds_between_retries)
            continue
        else:
            print(message)
            raise SystemExit(err)

corefile = re.sub(r'(?m)(^\s*)forward.*$', r'\1forward . %s {' % os.environ['NMN_LOAD_BALANCER_IP'], corefile)

corefile_patch = """
data:
  Corefile: |
{}
""".format(re.sub(r'(?m)^', r'    ', corefile))
with open('/tmp/patch.yaml', 'w') as f:
    f.write(corefile_patch)
with open('/tmp/patch.sh', 'w') as f:
    f.write('#!/bin/bash\nkubectl patch configmap {} -n {} -p "$(cat /tmp/patch.yaml)"'.format(os.environ['KUBERNETES_COREDNS_CONFIGMAP_NAME'], os.environ['KUBERNETES_COREDNS_NAMESPACE']))
shared.run_command(['chmod', '+x', '/tmp/patch.sh'])

print('Patching the CoreDNS configmap to forward to: {}'.format(os.environ['NMN_LOAD_BALANCER_IP']))
print(corefile_patch)
shared.run_command(['/bin/bash', '-c', '/tmp/patch.sh'])
print('Running a rolling restart of the CoreDNS deployment...')
shared.run_command(['kubectl', '-n', os.environ['KUBERNETES_COREDNS_NAMESPACE'], 'rollout', 'restart', 'deployment',
    os.environ['KUBERNETES_COREDNS_DEPLOYMENT_NAME']])
