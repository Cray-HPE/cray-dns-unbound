# cray-dns-unbound Helm chart

[Unbound](http://www.unbound.net) is a caching DNS resolver written in C. It is suitable for use as an upstream DNS resolver for kube-dns. The image is based on alpine and includes unbound, bind-tools and bash and is approximately 20MB in size, making for fast startup. Google's [healthz container](https://hub.docker.com/r/googlecontainer/exechealthz/) is used as a sidecar to probe the unbound container on localhost, which allows unbound to run in a default configuration with restricted network access, and still play nice with kubelet.

## Configuration

The chart values file contains the default settings for the unbound server. In the default configuration unbound will allow queries from localhost only, and will not have any forward zones. This means that queries sent to the ClusterIP of the service will return access denied, and queries from localhost for anything other than the health check record `health.check.unbound` will return NXDOMAIN.

You can configure unbound for your specific use case by passing a values file that contains the following properties. Most or all of these can also be set from the helm command line using `--set`.

### Access control

Controls which IP address ranges unbound will allow queries from. If you want to use unbound as an upstream for kube-dns, or allow other pods to query the resolver directly, you'll at least need to allow the `clusterIpV4Cidr` range.

```yaml
allowedIpRanges:
- "10.10.10.10/20"
- "10.10.11.11/20"
```

### Forward zones

You can set as many forward zones as needed by specifying the zone name and forward hosts. Forward hosts can be set by hostname or IP.

```yaml
forwardZones:
- name: "fake.net"
  forwardHosts:
  - "fake1.host.net"
  - "fake2.host.net"
- name: "stillfake.net"
  forwardIps:
  - "10.10.10.10"
  - "10.11.10.10"
```

### Local records

Unbound can store DNS records in a "local zone." This facility can be used to assign context-specific names to a given IP address, and could also be used for private DNS if you don't want or have an external resolver.

```yaml
localRecords:
- name: "fake3.host.net"
  ip: "10.12.10.10"
- name: "fake4.host.net"
  ip: "10.13.10.10"
```

### IPv6 Support

If IPv6 addresses have been configured on the Customer Management Network (CMN) then `cray-dns-unbound` can be configured to access an IPv6 DNS server by way of a network attachment definition. 
This is required because CSM currently does not deploy Kubernetes with dual-stack support.

| Property        | Default value | Description                                                                                                 |
| --------------- | ------------- | ----------------------------------------------------------------------------------------------------------- |
| ipv6.enabled    | false         | Enable/Disable IPv6 support                                                                                 |
| ipv6.interface  | bond0.cmn0    | Interface on the NCN Worker node used for the network attachment definition                                 |
| ipv6.gateway    | None          | The default gateway to use for IPv6 traffic. Must be set if `ipv6.enabled=true`                             |
| ipv6.subnet     | None          | The IPv6 subnet to use in CIDR form. Must be set if `ipv6.enabled=true`                                     |
| ipv6.rangeStart | None          | Start address of an IPv6 address pool to be used for `cray-dns-unbound`. Must be set if `ipv6.enabled=true` |
| ipv6.rangeEnd   | None          | End address of an IPv6 address pool to be used for `cray-dns-unbound`. Must be set if `ipv6.enabled=true`   |

The `rangeStart` and `rangeEnd` parameters define a pool of IP address to be used for cray-dns-unbound pods. This pool must be at least as large as `replicaCount` otherwise pods will fail to start
if there is no free IP address to be allocated.

### Other configurable properties

The following properties in values.yaml configure additional aspects of the unbound server. For more information see the [unbound documentation](http://unbound.net/documentation/unbound.conf.html).

```
unbound.verbosity: 1
unbound.numThreads: 1
unbound.statsInterval: 0
unbound.statsCumulative: no
unbound.serverPort: 53
```

### All configurable properties

| Property                 | Default value               |
| ------------------------ | --------------------------- |
| replicaCount             | 3                           |
| externalIP               | ""                          |
| clusterIP                | ""                          |
| unbound.image.repository | markbnj/unbound-docker      |
| unbound.image.tag        | 0.1.0                       |
| unbound.image.pullPolicy | IfNotPresent                |
| unbound.verbosity        | 1                           |
| unbound.numThreads       | 1                           |
| unbound.statsInterval    | 0                           |
| unbound.statsCumulative  | no                          |
| unbound.serverPort       | 53                          |
| healthz.image.repository | googlecontainer/exechealthz |
| healthz.image.tag        | 1.2                         |
| healthz.image.pullPolicy | IfNotPresent                |
| resources                | {}                          |
| nodeSelector             | {}                          |
| tolerations              | []                          |
| affinity                 | {}                          |
| allowedIpRanges          | []                          |
| forwardZones             | []                          |
| stubZones                | []                          |
| localRecords             | []                          |
| localZones               | []                          |

### Configuration changes

The unbound deployment template includes the sha256 hash of the configmap as an annotation. This will cause the deployment to update if the configuration is changed. For more information on this and other useful stuff see [chart tips and tricks](https://helm.sh/docs/howto/charts_tips_and_tricks/).

### Health checks

Liveness and readiness probes are implemented by a side-car [healthz container](https://github.com/kubernetes/contrib/tree/master/exec-healthz). When a http GET is made to port 8080 healthz runs an nslookup against the unbound server on localhost querying for the name `health.check.unbound` which is stored as a local record in the configuration.

## Configuring as an upstream resolver for kube-dns

To configure unbound to act as an upstream resolver for kube-dns edit the `kube-dns` configmap in the kube-system namespace to add the `stubDomains` value as shown below. The forwarding address for the domain should be set to the ClusterIP of the unbound service.

```yaml
apiVersion: v1
data:
  stubDomains: |
    {"fake.net": ["10.10.10.10"]}
kind: ConfigMap
metadata:
  creationTimestamp: 2018-01-04T18:09:38Z
  labels:
    addonmanager.kubernetes.io/mode: EnsureExists
  name: kube-dns
  namespace: kube-system
  resourceVersion: "1825"
  selfLink: /api/v1/namespaces/kube-system/configmaps/kube-dns
  uid: 6d759f7d-f17a-11e7-898d-42010a800159
```
