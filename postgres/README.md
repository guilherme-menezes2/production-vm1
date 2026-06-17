# PostgreSQL VM1

Quando `production-vm1/` for publicado como repositorio GitHub independente, copie ou gere aqui as migrations necessarias em `postgres/migrations/`.

Durante o desenvolvimento local no monorepo, as migrations principais ficam em `../postgres/migrations/`. O script `scripts/migrate.sh` tenta primeiro `production-vm1/postgres/migrations/` e depois o fallback do monorepo.

Em producao, aplique migrations com cuidado e backup previo. Dados reais ficam em `../data/postgres/` e nao devem ser versionados.
