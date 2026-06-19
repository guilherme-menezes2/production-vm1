#!/usr/bin/env sh
set -eu

: "${RADIUS_SECRET:?RADIUS_SECRET nao definido}"
: "${RADIUS_CLIENT_IP:?RADIUS_CLIENT_IP nao definido}"
: "${POSTGRES_HOST:=postgres}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_DB:?POSTGRES_DB nao definido}"
: "${POSTGRES_USER:?POSTGRES_USER nao definido}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD nao definido}"

if [ -d /etc/raddb ]; then
  RADIUS_CONF_DIR=/etc/raddb
elif [ -d /etc/freeradius/3.0 ]; then
  RADIUS_CONF_DIR=/etc/freeradius/3.0
else
  echo "Diretorio de configuracao do FreeRADIUS nao encontrado." >&2
  exit 1
fi

mkdir -p "$RADIUS_CONF_DIR/mods-available" "$RADIUS_CONF_DIR/mods-enabled" /var/log/radius

cat > "$RADIUS_CONF_DIR/clients.conf" <<EOF
client localhost_ipv4 {
  ipaddr = 127.0.0.1
  secret = ${RADIUS_SECRET}
  require_message_authenticator = no
  limit_proxy_state = no
  proto = *
}

client localhost_ipv6 {
  ipv6addr = ::1
  secret = ${RADIUS_SECRET}
  require_message_authenticator = no
  limit_proxy_state = no
  proto = *
}

client mikrotik_production {
  ipaddr = ${RADIUS_CLIENT_IP}
  secret = ${RADIUS_SECRET}
  require_message_authenticator = no
  limit_proxy_state = no
  proto = *
}
EOF

cat > "$RADIUS_CONF_DIR/mods-available/sql" <<EOF
sql {
  driver = "rlm_sql_postgresql"
  dialect = "postgresql"

  server = "${POSTGRES_HOST}"
  port = ${POSTGRES_PORT}
  login = "${POSTGRES_USER}"
  password = "${POSTGRES_PASSWORD}"
  radius_db = "${POSTGRES_DB}"

  read_clients = no
  client_table = "nas"
  group_attribute = "SQL-Group"
  read_groups = yes
  delete_stale_sessions = yes

  acct_table1 = "radacct"
  acct_table2 = "radacct"
  postauth_table = "radpostauth"
  authcheck_table = "radcheck"
  groupcheck_table = "radgroupcheck"
  authreply_table = "radreply"
  groupreply_table = "radgroupreply"
  usergroup_table = "radusergroup"

  pool {
    start = 2
    min = 1
    max = 10
    spare = 2
    uses = 0
    retry_delay = 5
    lifetime = 0
    idle_timeout = 60
  }

  \$INCLUDE \${modconfdir}/\${.:name}/main/\${dialect}/queries.conf
}
EOF

ln -sf ../mods-available/sql "$RADIUS_CONF_DIR/mods-enabled/sql"

if command -v radiusd >/dev/null 2>&1; then
  RADIUS_BIN=radiusd
elif command -v freeradius >/dev/null 2>&1; then
  RADIUS_BIN=freeradius
else
  echo "Binario do FreeRADIUS nao encontrado." >&2
  exit 1
fi

if [ "$#" -gt 0 ]; then
  case "$1" in
    radiusd|freeradius)
      exec "$@"
      ;;
    -*)
      exec "$RADIUS_BIN" "$@"
      ;;
    *)
      exec "$@"
      ;;
  esac
fi

exec "$RADIUS_BIN" -f -l /var/log/radius/radius.log
