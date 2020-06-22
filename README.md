# The Cray DNS Resolver Service Using Unbound

[Unbound](https://unbound.net/) is a validating, recursive, and caching DNS resolver.

### TODO:

* there are no tests in this, they should be built out. In the meantime, it's the developer's job to ensure due diligence to test for new stuff as well as regression
* Account for hostnames that end up being removed from Kea/DHCP. Right now, those will stick around indefinitely in DNS, which shouldn't present any problems at this stage, but worth noting (see `./manager.py` related TODO)
