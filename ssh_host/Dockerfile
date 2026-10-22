FROM alpine:3.20
# sshd та docker CLI для імітації Linux VM з Docker
RUN apk add --no-cache openssh-server docker-cli docker-cli-compose bash shadow \
    && adduser -D -s /bin/bash lab \
    && echo "lab:$(head -c 24 /dev/urandom | base64)" | chpasswd \
    && mkdir -p /run/sshd
COPY sshd_config /etc/ssh/sshd_config.d/90-lab2.conf
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh && rm -f /etc/ssh/ssh_host_*
EXPOSE 22
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
