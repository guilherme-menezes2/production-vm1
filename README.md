# Production VM1

Esta pasta contem o scaffold de producao da VM1, responsavel pelos servicos de tempo real do hotspot.

## Servicos

- Portal
- FreeRADIUS
- PostgreSQL principal
- Nginx
- rsyslog
- backup-client

O PostgreSQL principal fica somente nesta VM e nao e publicado em porta do host. A VM2 nao participa da autenticacao em tempo real; se a VM2 cair, Portal e FreeRADIUS continuam funcionando na VM1. Apenas backups ficarao indisponiveis ate a VM2 retornar.

## Primeiro uso

Este diretorio foi preparado para ser usado como um repositorio GitHub independente da VM1.

Antes de publicar ou atualizar o repo da VM1, confirme que ele contem tudo que o compose precisa para buildar em producao:

- codigo buildavel do portal em `portal/`, incluindo `portal/Dockerfile`;
- migrations em `postgres/migrations/`;
- configuracoes de `nginx/`, `freeradius/`, `rsyslog/` e `backup-client/`.

No servidor:

```sh
git clone git@github.com:<ORG>/<REPO_VM1>.git /opt/hotspot-academia/production-vm1
cd /opt/hotspot-academia/production-vm1
```

```sh
cp .env.example .env
```

Edite `.env` e troque todos os valores `CHANGE_ME_*`.

Se os scripts chegarem sem permissao de execucao no Debian 12:

```sh
chmod +x scripts/*.sh
```

Variaveis principais:

- `PORTAL_DOMAIN`: dominio publico do portal, usado pelo Nginx e pelo Portal.
- `VM1_PUBLIC_IP`: IP onde Nginx, FreeRADIUS e rsyslog ficarao publicados.
- `CCR_IP`: IP da CCR1036/NAS autorizado no FreeRADIUS.
- `BACKUP_REPOSITORY`: repositorio restic remoto na VM2.
- `RESTIC_PASSWORD`: senha de criptografia do backup.

## Operacao

```sh
./scripts/start.sh
```

Se o build falhar com `failed to read dockerfile: open Dockerfile: no such file or directory`, o repositorio da VM1 foi publicado sem o conteudo buildavel de `portal/`. Atualize o repo incluindo `portal/Dockerfile`, `portal/app.py`, `portal/requirements.txt` e `portal/static/`.

```sh
./scripts/status.sh
```

```sh
./scripts/logs.sh
```

Para ver logs de um servico especifico:

```sh
./scripts/logs.sh portal
```

## Banco

Aplicar migrations:

```sh
./scripts/migrate.sh
```

Checar conexao interna do PostgreSQL:

```sh
./scripts/check-db.sh
```

## FreeRADIUS

Verificar se o FreeRADIUS esta em execucao:

```sh
./scripts/check-radius.sh
```

As portas UDP `1812` e `1813` sao publicadas para a CCR/NAS. Em firewall de host, security group ou borda, restrinja essas portas somente ao `CCR_IP`.

Exemplo conceitual:

```sh
# permitir UDP 1812/1813 somente da CCR
# bloquear demais origens
```

## rsyslog

A porta UDP `514` recebe logs da CCR. Em firewall de host, security group ou borda, restrinja essa porta somente ao `CCR_IP`.

## Backup

Checar conectividade com a VM2:

```sh
./scripts/check-vm2-connection.sh
```

Executar backup manual:

```sh
./scripts/backup.sh
```

Para repositorio restic via SFTP/SSH, coloque a chave privada e o `known_hosts` em `data/backups/ssh/`, pois esse diretorio e montado como `/root/.ssh` no container `backup-client`.

Listar snapshots:

```sh
./scripts/backup-list.sh
```

Testar restore em area temporaria:

```sh
./scripts/restore-test.sh
```

## Dados Persistentes

Dados reais ficam em `production-vm1/data/` e nao devem ser versionados. O `.gitignore` deste repositorio ja ignora esses caminhos:

- banco PostgreSQL
- uploads/assets do portal
- logs do Nginx, FreeRADIUS e rsyslog
- dumps temporarios de backup

Volumes usados pelo compose:

- `./data/postgres`
- `./data/portal`
- `./data/freeradius`
- `./data/nginx`
- `./data/rsyslog`
- `./data/backups`

## Testes Da VM1

Validar compose:

```sh
docker compose --env-file .env -f docker-compose.yml config
```

Subir e verificar:

```sh
./scripts/start.sh
./scripts/status.sh
./scripts/check-db.sh
./scripts/check-radius.sh
./scripts/check-vm2-connection.sh
```

Testar HTTP localmente na VM:

```sh
curl -I http://127.0.0.1/health
```

## Seguranca

- Nao use senhas dos exemplos.
- Defina `PORTAL_SHOW_RADIUS_PASSWORD=false`.
- Publique Nginx com HTTPS real antes de abrir para usuarios.
- Restrinja UDP 1812/1813 ao IP da CCR/NAS.
- Restrinja UDP 514 aos roteadores autorizados.
- Use rede privada/VPN para acessar a VM2 de backup.
