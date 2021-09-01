FROM arti.dev.cray.com/baseos-docker-master-local/alpine:3.13.5

ENV UNBOUND_CONFIG_DIRECTORY=/etc/unbound

RUN apk add --no-cache bash python3 py-pip
RUN cp /etc/apk/repositories /etc/apk/repositories.bak
RUN echo "http://dl-4.alpinelinux.org/alpine/latest-stable/main/" >> /etc/apk/repositories && \
    apk add --no-cache unbound
RUN mv /etc/apk/repositories.bak /etc/apk/repositories

RUN pip3 install --upgrade pip
RUN pip3 install requests PyYAML

RUN wget -q https://storage.googleapis.com/kubernetes-release/release/v1.18.3/bin/linux/amd64/kubectl -O /usr/bin/kubectl \
    && chmod +x /usr/bin/kubectl

RUN mkdir -p ${UNBOUND_CONFIG_DIRECTORY} && \
    mkdir -p /srv/unbound && \
    mkdir -p /var/run/unbound

COPY unbound.conf ${UNBOUND_CONFIG_DIRECTORY}/unbound.conf
COPY entrypoint.sh shared.py initialize.py manager.py coredns.py /srv/unbound/
RUN chmod +x /srv/unbound/entrypoint.sh && \
    chmod +x /srv/unbound/initialize.py && \
    chmod +x /srv/unbound/manager.py && \
    chmod +x /srv/unbound/coredns.py
RUN echo "[]" > ${UNBOUND_CONFIG_DIRECTORY}/records.json

RUN chown -R unbound /srv/unbound
RUN chown -R unbound /etc/unbound
RUN chown -R unbound /var/run/unbound

EXPOSE 5053/udp
EXPOSE 5053/tcp

USER unbound
ENTRYPOINT ["/srv/unbound/entrypoint.sh"]
