# Portal VM1

Quando `production-vm1/` for publicado como repositorio GitHub independente, este diretorio deve conter o codigo buildavel do portal, incluindo `Dockerfile` e arquivos da aplicacao.

O compose de producao usa `./portal` como build context para nao depender do monorepo local.

Dados persistentes do portal, incluindo uploads/assets do page builder, ficam em `../data/portal/` e entram no backup.
