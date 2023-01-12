FROM artifactory.algol60.net/docker.io/library/golang:1.19-alpine AS build-base

RUN set -ex \
    && apk update \
    && apk add --no-cache \
        build-base \
        git

# Base copies in the files we need to test/build.
FROM build-base AS base

WORKDIR /build

# Copy all the necessary files to the image.
COPY unbound_exporter/ .

### Build Stage ###
FROM base AS builder

ARG go_build_args="-mod=vendor"

RUN set -ex \
    && go build ${go_build_args} -v -o /usr/local/bin/unbound_exporter .

# Pinned to alpine:3.13 because alpine:3.14+ requires Docker 20.10.0 or newer,
# see https://wiki.alpinelinux.org/wiki/Release_Notes_for_Alpine_3.14.0
FROM artifactory.algol60.net/csm-docker/stable/docker.io/library/alpine:3


ENV UNBOUND_CONFIG_DIRECTORY=/etc/unbound
ENV UNBOUND_CONTROL_INTERFACE=127.0.0.1
ENV UNBOUND_PORT=8953

RUN apk update && apk add --no-cache bash python3 py3-pip unbound  && \
    pip3 install --upgrade pip && pip3 install requests PyYAML

# separate section to install dnsperf due to the edge repo of python is 3.11.0 breaks pip3 package
RUN echo "http://dl-cdn.alpinelinux.org/alpine/edge/main" >> /etc/apk/repositories && \
    echo "http://dl-cdn.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories && \
    echo "http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories && \
    apk update && apk add --no-cache ldns libcrypto3 libssl3 musl nghttp2-libs dnsperf

RUN wget -q https://storage.googleapis.com/kubernetes-release/release/v1.20.11/bin/linux/amd64/kubectl -O /usr/bin/kubectl \
    && chmod +x /usr/bin/kubectl

COPY --from=builder /usr/local/bin/unbound_exporter /usr/local/bin

RUN mkdir -p ${UNBOUND_CONFIG_DIRECTORY} && \
    mkdir -p /srv/unbound && \
    mkdir -p /var/run/unbound

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
