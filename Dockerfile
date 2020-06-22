FROM dtr.dev.cray.com/cache/alpine:3.8

ENV UNBOUND_CONFIG_DIRECTORY=/etc/unbound

RUN apk add --no-cache bash python3
RUN echo "http://dl-4.alpinelinux.org/alpine/latest-stable/main/" >> /etc/apk/repositories && \
    apk add --no-cache unbound

RUN pip3 install --upgrade pip
RUN pip3 install requests

RUN wget -q https://storage.googleapis.com/kubernetes-release/release/v1.18.3/bin/linux/amd64/kubectl -O /usr/bin/kubectl \
    && chmod +x /usr/bin/kubectl

RUN mkdir -p ${UNBOUND_CONFIG_DIRECTORY} && \
    mkdir -p /srv/unbound && \
    mkdir -p /var/run/unbound

COPY unbound.conf ${UNBOUND_CONFIG_DIRECTORY}/unbound.conf
COPY entrypoint.sh initialize.py manager.py /srv/unbound/
RUN chmod +x /srv/unbound/entrypoint.sh && \
    chmod +x /srv/unbound/initialize.py && \
    chmod +x /srv/unbound/manager.py
RUN echo "[]" > ${UNBOUND_CONFIG_DIRECTORY}/records.json

EXPOSE 5053/udp

ENTRYPOINT ["/srv/unbound/entrypoint.sh"]
