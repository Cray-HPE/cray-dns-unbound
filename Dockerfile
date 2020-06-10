FROM alpine:3.10 as build

ARG UNBOUND_VERSION=unbound-1.10.1
ARG UNBOUND_SOURCE=https://www.nlnetlabs.nl/downloads/unbound/
ARG UNBOUND_SHA1=9932931d495248b4e45d278b4679efae29238772
ARG LDNS_VERSION=ldns-1.7.1
ARG LDNS_SOURCE=https://www.nlnetlabs.nl/downloads/ldns/
ARG LDNS_SHA1=d075a08972c0f573101fb4a6250471daaa53cb3e

SHELL ["/bin/ash", "-eo", "pipefail", "-c"]

RUN apk add --no-cache \
    build-base=0.5-r1 \
    curl=7.66.0-r0 \
    expat-dev=2.2.8-r0 \
    libevent-dev=2.1.10-r0 \
    libevent-static=2.1.10-r0 \
    linux-headers=4.19.36-r0 \
    openssl-dev=1.1.1g-r0 \
    perl=5.28.2-r1

WORKDIR /tmp/unbound

RUN curl -fsSL --retry 3 "${UNBOUND_SOURCE}${UNBOUND_VERSION}.tar.gz" -o unbound.tar.gz \
    && echo "${UNBOUND_SHA1}  unbound.tar.gz" | sha1sum -c - \
    && tar xzf unbound.tar.gz --strip 1 \
    && ./configure --with-pthreads --with-libevent --prefix=/opt/unbound --with-run-dir=/var/run/unbound --with-username= --with-chroot-dir= --enable-fully-static --disable-shared --enable-event-api --disable-flto \
    && make -j 4 install

WORKDIR /tmp/ldns

RUN curl -fsSL --retry 3 "${LDNS_SOURCE}${LDNS_VERSION}.tar.gz" -o ldns.tar.gz \
    && echo "${LDNS_SHA1}  ldns.tar.gz" | sha1sum -c - \
    && tar xzf ldns.tar.gz --strip 1 \
    && sed -e 's/@LDFLAGS@/@LDFLAGS@ -all-static/' -i Makefile.in \
    && ./configure --prefix=/opt/ldns --with-drill --disable-shared \
    && make -j 4 \
    && make install

WORKDIR /var/run/unbound

RUN mv /opt/unbound/etc/unbound/unbound.conf /opt/unbound/etc/unbound/example.conf \
    && rm -rf /tmp/* /opt/*/include /opt/*/man /opt/*/share \
    && strip /opt/unbound/sbin/unbound \
    && strip /opt/ldns/bin/drill \
    && (/opt/unbound/sbin/unbound-anchor -v || :)

# ----------------------------------------------------------------------------

FROM alpine:3.10

RUN apk add --no-cache bash python3

COPY --from=build /etc/passwd /etc/group /etc/
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=build /lib/ld-musl-*.so.1 /lib/

COPY --from=build /opt /opt
COPY --from=build --chown=nobody:nogroup /var/run/unbound /var/run/unbound

COPY unbound.conf /opt/unbound/etc/unbound/
COPY entrypoint.sh update-records.py /opt/unbound/
RUN chmod +x /opt/unbound/entrypoint.sh && \
    chmod +x /opt/unbound/update-records.py
RUN echo "# A records will get filled in here" > /opt/unbound/etc/unbound/a-records.conf
RUN echo "" > /opt/unbound/etc/unbound/a-records.conf.sum && \
    chown nobody:nogroup /opt/unbound/etc/unbound/a-records.conf && \
    chown nobody:nogroup /opt/unbound/etc/unbound/a-records.conf.sum

EXPOSE 5353/udp

USER nobody

ENV PATH /opt/unbound/sbin:/opt/ldns/bin:${PATH}

ENTRYPOINT ["/opt/unbound/entrypoint.sh"]
RUN ["unbound", "-V"]
RUN ["drill", "-v"]
