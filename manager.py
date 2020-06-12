#!/usr/bin/env python3

print('Querying Kea in the cluster to find any updated records we need to set')
# TODO: build out records mgr here:
#  1. Query Kea to get current state of reservations
#  2. Get our cray-dns-unbound configmap storing our unbound A records JSON
#  3. Determine if any diff exists between Kea's reservation set, and what we know about in the a records JSON
#     a. If no diff, we can exit this job
#     b. If there is a diff...
# 4. modify our local A records JSON data set and kubectl patch the configmap with the updated set
# 5. `kubectl rollout restart` our deployment so that the deployment pods/containers can begin to restart with the newer A records
