FROM alpine:3.20

RUN apk add --no-cache rsyslog tzdata

COPY rsyslog.conf /etc/rsyslog.conf

RUN mkdir -p /var/log/remote /var/spool/rsyslog

EXPOSE 514/udp

CMD ["rsyslogd", "-n", "-f", "/etc/rsyslog.conf"]
