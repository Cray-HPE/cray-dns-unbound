FROM rust:1 AS builder


ADD unbound-telemetry/ /unbound-telemetry
WORKDIR /unbound-telemetry
# We can't use the `rust:alpine` image directly,
# because we have proc macros crates in the dependency tree
# and they can't be compiled directly on musl systems.
# Cross compiling works, though, so here we are.
RUN apt-get update && \
    apt-get install -y musl-tools && \
    rustup target add x86_64-unknown-linux-musl && \
    cargo build --release --target=x86_64-unknown-linux-musl --features vendored && \
    strip ./target/x86_64-unknown-linux-musl/release/unbound-telemetry


# Pinned to alpine:3.13 because alpine:3.14+ requires Docker 20.10.0 or newer,
# see https://wiki.alpinelinux.org/wiki/Release_Notes_for_Alpine_3.14.0
FROM artifactory.algol60.net/csm-docker/stable/docker.io/library/alpine:3

#####
### temp tooling

ENV CONCURRENCY_KIT_VERSION 0.7.0
ENV DNSPERF_VERSION 2.9.0

RUN apk add --no-cache                                                        \
        bind                                                                  \
        bind-dev                                                              \
        g++                                                                   \
        json-c-dev                                                            \
        krb5-dev                                                              \
        libcap-dev                                                            \
        libxml2-dev                                                           \
        make                                                                  \
        nghttp2-dev                                                           \
        openssl-dev



# http://concurrencykit.org/
ADD https://github.com/concurrencykit/ck/archive/refs/tags/${CONCURRENCY_KIT_VERSION}.tar.gz /opt/
RUN cd /opt && tar -zxf /opt/${CONCURRENCY_KIT_VERSION}.tar.gz -C /opt/ \
 && cd ck-${CONCURRENCY_KIT_VERSION} \
 && ./configure && make install clean && cd .. \
 && rm -rvf ck-${CONCURRENCY_KIT_VERSION} \
 && rm -rvf /opt/${CONCURRENCY_KIT_VERSION}.tar.gz

# https://www.dns-oarc.net/tools/dnsperf
ADD https://www.dns-oarc.net/files/dnsperf/dnsperf-${DNSPERF_VERSION}.tar.gz /opt/
RUN cd /opt && tar -zxf /opt/dnsperf-${DNSPERF_VERSION}.tar.gz -C /opt/ \
 && cd /opt/dnsperf-${DNSPERF_VERSION} \
 && ./configure && make install distclean && cd .. \
 && rm -rvf /opt/dnsperf-${DNSPERF_VERSION} \
 && rm -rvf /opt/dnsperf-${DNSPERF_VERSION}.tar.gz
####

ENV UNBOUND_CONFIG_DIRECTORY=/etc/unbound
ENV UNBOUND_CONTROL_INTERFACE=127.0.0.1
ENV UNBOUND_PORT=8953

RUN apk update && apk add --no-cache bash python3 py-pip unbound && \
pip3 install --upgrade pip && pip3 install requests PyYAML

RUN wget -q https://storage.googleapis.com/kubernetes-release/release/v1.20.11/bin/linux/amd64/kubectl -O /usr/bin/kubectl \
    && chmod +x /usr/bin/kubectl

RUN mkdir -p ${UNBOUND_CONFIG_DIRECTORY} && \
    mkdir -p /srv/unbound && \
    mkdir -p /var/run/unbound

COPY --from=builder /unbound-telemetry/target/x86_64-unknown-linux-musl/release/unbound-telemetry /bin
COPY unbound.conf ${UNBOUND_CONFIG_DIRECTORY}/unbound.conf
COPY kubernetes/cray-dns-unbound/files/*.* /srv/unbound/
RUN chmod +x /srv/unbound/entrypoint.sh && \
    chmod +x /srv/unbound/initialize.py && \
    chmod +x /srv/unbound/manager.py && \
    chmod +x /srv/unbound/coredns.py
RUN echo "[]" > ${UNBOUND_CONFIG_DIRECTORY}/records.json
RUN gzip ${UNBOUND_CONFIG_DIRECTORY}/records.json
RUN touch ${UNBOUND_CONFIG_DIRECTORY}/records.conf

RUN chown -R unbound /srv/unbound
RUN chown -R unbound /etc/unbound
RUN chown -R unbound /var/run/unbound

EXPOSE 5053/udp
EXPOSE 5053/tcp
EXPOSE 80/udp
EXPOSE 80/tcp
USER unbound
ENTRYPOINT ["/srv/unbound/entrypoint.sh"]