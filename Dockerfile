FROM rust:1.54.0 AS builder


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
FROM artifactory.algol60.net/docker.io/library/alpine:3.15

ENV UNBOUND_CONFIG_DIRECTORY=/etc/unbound
ENV UNBOUND_CONTROL_INTERFACE=127.0.0.1
ENV UNBOUND_PORT=8953

RUN apk add --no-cache bash python3 py-pip unbound=1.13.2-r2

RUN pip3 install --upgrade pip
RUN pip3 install requests PyYAML

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

RUN chown -R unbound.unbound /srv/unbound
RUN chown -R unbound.unbound /etc/unbound
RUN chown -R unbound.unbound /var/run/unbound

EXPOSE 5053/udp
EXPOSE 5053/tcp
EXPOSE 80/udp
EXPOSE 80/tcp
USER unbound
ENTRYPOINT ["/srv/unbound/entrypoint.sh"]
