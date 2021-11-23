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


FROM arti.dev.cray.com/baseos-docker-master-local/alpine:3.13.5

ENV UNBOUND_CONFIG_DIRECTORY=/etc/unbound
ENV UNBOUND_CONTROL_INTERFACE=127.0.0.1
ENV UNBOUND_PORT=8953

RUN apk add --no-cache bash python3 py-pip unbound=1.13.2-r0

RUN pip3 install --upgrade pip
RUN pip3 install requests PyYAML

RUN wget -q https://storage.googleapis.com/kubernetes-release/release/v1.18.3/bin/linux/amd64/kubectl -O /usr/bin/kubectl \
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

RUN chown -R unbound /srv/unbound
RUN chown -R unbound /etc/unbound
RUN chown -R unbound /var/run/unbound

EXPOSE 5053/udp
EXPOSE 5053/tcp
EXPOSE 80/udp
EXPOSE 80/tcp
USER unbound
