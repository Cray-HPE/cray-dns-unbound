#!/usr/bin/env bash

version_match=true

image_version=$(cat .version)
chart_app_version=$(yq eval .appVersion kubernetes/cray-dns-unbound/Chart.yaml)
chart_image_version=$(cat kubernetes/cray-dns-unbound/Chart.yaml |grep image:|cut -d ':' -f3)
chart_values_global_chart_version=$(yq eval .global.chart.version kubernetes/cray-dns-unbound/values.yaml)
chart_values_global_app_version=$(yq eval .global.appVersion kubernetes/cray-dns-unbound/values.yaml)

if [[ "$image_version" != "$chart_app_version" ]];then
    printf "ERROR: version mismatch\n"
    printf "image_version $image_version\n"
    printf "chart_app_version $chart_app_version\n"
    version_match=false
fi

if [[ "$image_version" != "$chart_image_version" ]];then
    printf "ERROR: version mismatch\n"
    printf "image_version $image_version\n"
    printf "chart_image_version $chart_image_version\n"
    version_match=false
fi

if [[ "$image_version" != "$chart_values_global_chart_version" ]];then
    printf "ERROR: version mismatch\n"
    printf "image_version $image_version\n"
    printf "chart_values_global_chart_version $chart_values_global_chart_version\n"
    version_match=false
fi

if [[ "$image_version" != "$chart_values_global_app_version" ]];then
    printf "ERROR: version mismatch\n"
    printf "image_version $image_version\n"
    printf "chart_values_global_app_version $chart_values_global_app_version\n"
    version_match=false
fi

if $version_match;then
    printf "Versions all match\n"
else
    printf "\nERROR: version mismatch, see above output\n"
fi