FROM alpine:3.20

RUN apk add --no-cache openssh-client restic postgresql16-client tzdata

COPY backup-now.sh /opt/backup/backup-now.sh
COPY backup-list.sh /opt/backup/backup-list.sh
COPY restore-latest-test.sh /opt/backup/restore-latest-test.sh

RUN chmod +x /opt/backup/*.sh \
  && mkdir -p /backups /restore-test

CMD ["tail", "-f", "/dev/null"]
