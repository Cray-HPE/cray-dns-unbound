#!/usr/bin/env bash

header=$(basename $0)

#
# Set manifest version
# NOTE: Hash should be underscore version!
version="0.1.12-20210410210058_7b0964e"
version_plus=$(echo ${version} | tr '_' '+')
echo "${header}: Updating to Unbound version ${version}"
echo


#
# Directory check
#
dir=$(pwd)
echo "${header}: Running from ${dir}"
echo


#
# Add safety entries to /etc/hosts since we're taking down DNS
# while still needing DNS
#
echo "${header}: Adding safety entries for packages and registry to /etc/hosts"
hosts_record="10.92.100.71 packages.local registry.local"
grep "${hosts_record}" /etc/hosts 2>&1>>/dev/null
if [[ $? != 0 ]];then
    echo "${hosts_record}" >> /etc/hosts 
fi



#
# Write manifest with proper version
# NOTE: No forwarder here - patch it later
#
manifest="${dir}/unbound.yaml"
echo "${header}: Writing Unbound manifest to ${manifest}"
cat <<MANIFEST > ${manifest}
apiVersion: manifests/v1beta1
metadata:
  name: unbound
spec:
  charts:
  - name: cray-dns-unbound
    namespace: services
    values:
      global:
        appVersion: ${version}
      imageHost: registry.local
    version: ${version_plus}
MANIFEST
if [[ ! -e ${dir}/unbound.yaml ]];then
    echo "${dir}/unbound.yaml does not exist"
    echo "Corrrect the issue and re-run this script"
    exit 1
fi
echo


#
# Get the running unbound.conf from the configmap
# NOTE: This is what will bring in required forwarders
#
echo "${header}: Retrieving unbound.conf from configmap"
echo "${header}: =========="
kubectl get configmap -n services cray-dns-unbound -o json | jq '.data | .["unbound.conf"]' | tee ${dir}/unbound.conf
echo "${header}: =========="
if [[ ! -e ${dir}/unbound.conf ]];then
    echo "${dir}/unbound.conf does not exist"
    echo "Corrrect the issue and re-run this script"
    exit 1
fi
echo


#
# Upload docker image to packages and tag it
#
echo "${header}: Uploading docker image ${version} to local registry"
podman run --rm --network host -v ${dir}/images:/images registry.local/skopeo/stable copy --dest-tls-verify=false docker-archive:/images/cray-dns-unbound-${version}-dockerimage.tar docker://registry.local/cray/cray-dns-unbound:${version}
#podman run -v /root/slynn/helm:/helm --rm --network host -e NEXUS_URL="https://packages.local" dtr.dev.cray.com/cray/cray-nexus-setup:0.4.0 "nexus-upload-repo-helm" "/helm"/ "charts"
if [[ $? != 0 ]];then
    echo "An error occurred uploading the image to registry.local"
    echo "Correct the issue and re-run this script"
    exit 1
fi
echo


#
# Patch configmap since the old records.json won't be removed and this can cause issues
#
echo "${header} Truncating records.json in existing configmap since these values may cause issues"
kubectl -n services patch configmaps cray-dns-unbound --type merge -p '{"data":{"records.json":"[]"}}'
echo


#
# Full update via loftsman
# 
echo "${header}: Deploying new image version ${version} with chart in ${dir}/charts/"
loftsman ship --charts-path ${dir}/charts/ --manifest-path ${dir}/unbound.yaml
echo


#
# Patch configmap since the old records.json won't be removed and this can cause issues
#
echo "${header} Removing records.json key from configmap since it has been replaced with records.json.gz"
kubectl -n services patch configmap cray-dns-unbound --type=json -p='[{"op": "remove", "path": "/data/records.json"}]'
echo


#
# Patch configmap to apply any original forwarder settings
#
echo "${header} Patching configmap to apply any original forwarder settings"
patch="{\"data\":{\"unbound.conf\":$(cat ${dir}/unbound.conf)}}"
kubectl -n services patch configmaps cray-dns-unbound --type merge -p "${patch}"
echo



#
# Remove safety entries to /etc/hosts 
#
echo "${header}: Removing safety entries for packages and registry to /etc/hosts"
grep "${hosts_record}" /etc/hosts 2>&1>>/dev/null
if [[ $? == 0 ]];then
    grep -v "${hosts_record}" /etc/hosts >> /etc/hosts.tmp
    mv /etc/hosts.tmp /etc/hosts
fi
echo


#
# If something went wrong....
#
echo "This deployment may take 5-15 minutes to fully roll out."
echo "If something seems to have gone wrong you can fully roll back"
echo "to the previous version by running:"
echo "    helm rollback -n services cray-dns-unbound"
echo "and possibly patch the configmap with:"
echo "    records.json = \"[]\""
echo
echo "To aid beyond that the unbound-0.1.11.yaml manifest is provided"
echo "as well as example unbound.conf that has a forwarder and can be"
echo "manually placed in the configmap."


# To reset records in new records.json.gz:
# kubectl -n services patch configmaps cray-dns-unbound --type merge -p '{"data":{"records.json.gz":"H4sICLQ/Z2AAA3JlY29yZHMuanNvbgCLjuUCAETSaHADAAAA"}}'
