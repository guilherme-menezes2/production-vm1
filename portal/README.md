# Portal VM1

Este diretorio contem o codigo buildavel do portal usado em producao, incluindo `Dockerfile` e arquivos da aplicacao.

O compose de producao usa `./portal` como build context para nao depender do monorepo local.

Dados persistentes do portal, incluindo uploads/assets do page builder, ficam em `../data/portal/` e entram no backup.
