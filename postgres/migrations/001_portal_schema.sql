BEGIN;

CREATE TABLE IF NOT EXISTS clientes (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nome TEXT NOT NULL,
  documento TEXT NOT NULL,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT clientes_documento_unique UNIQUE (documento)
);

CREATE TABLE IF NOT EXISTS unidades (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cliente_id BIGINT NOT NULL REFERENCES clientes(id) ON DELETE RESTRICT,
  nome TEXT NOT NULL,
  identificador TEXT NOT NULL,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT unidades_cliente_identificador_unique UNIQUE (cliente_id, identificador)
);

CREATE TABLE IF NOT EXISTS usuarios (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unidade_id BIGINT NOT NULL REFERENCES unidades(id) ON DELETE RESTRICT,
  nome TEXT NOT NULL,
  telefone TEXT,
  cpf TEXT,
  username_radius TEXT NOT NULL,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT usuarios_username_radius_unique UNIQUE (username_radius)
);

CREATE TABLE IF NOT EXISTS dispositivos (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  mac TEXT NOT NULL,
  primeiro_acesso TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ultimo_acesso TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT dispositivos_usuario_mac_unique UNIQUE (usuario_id, mac)
);

CREATE TABLE IF NOT EXISTS termos_aceite (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  versao_termo TEXT NOT NULL,
  ip_aceite INET,
  mac_aceite TEXT,
  user_agent TEXT,
  aceito_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admin_users (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  nome TEXT NOT NULL,
  email TEXT NOT NULL,
  senha_hash TEXT NOT NULL,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT admin_users_email_unique UNIQUE (email),
  CONSTRAINT admin_users_senha_hash_minima CHECK (LENGTH(senha_hash) >= 40)
);

CREATE TABLE IF NOT EXISTS admin_logs (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  admin_user_id BIGINT REFERENCES admin_users(id) ON DELETE SET NULL,
  acao TEXT NOT NULL,
  entidade TEXT,
  entidade_id TEXT,
  ip_origem INET,
  user_agent TEXT,
  detalhes JSONB NOT NULL DEFAULT '{}'::jsonb,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS login_auditoria (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  usuario_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
  username_radius TEXT,
  mac TEXT,
  ip_interno INET,
  nas_ip INET,
  resultado TEXT NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usuarios_cpf ON usuarios (cpf);
CREATE INDEX IF NOT EXISTS idx_usuarios_telefone ON usuarios (telefone);
CREATE INDEX IF NOT EXISTS idx_usuarios_username_radius ON usuarios (username_radius);

CREATE INDEX IF NOT EXISTS idx_dispositivos_mac ON dispositivos (mac);
CREATE INDEX IF NOT EXISTS idx_dispositivos_primeiro_acesso ON dispositivos (primeiro_acesso);
CREATE INDEX IF NOT EXISTS idx_dispositivos_ultimo_acesso ON dispositivos (ultimo_acesso);

CREATE INDEX IF NOT EXISTS idx_termos_aceite_mac ON termos_aceite (mac_aceite);
CREATE INDEX IF NOT EXISTS idx_termos_aceite_aceito_em ON termos_aceite (aceito_em);

CREATE INDEX IF NOT EXISTS idx_admin_logs_admin_user_id ON admin_logs (admin_user_id);
CREATE INDEX IF NOT EXISTS idx_admin_logs_criado_em ON admin_logs (criado_em);

CREATE INDEX IF NOT EXISTS idx_login_auditoria_usuario_id ON login_auditoria (usuario_id);
CREATE INDEX IF NOT EXISTS idx_login_auditoria_username_radius ON login_auditoria (username_radius);
CREATE INDEX IF NOT EXISTS idx_login_auditoria_mac ON login_auditoria (mac);
CREATE INDEX IF NOT EXISTS idx_login_auditoria_criado_em ON login_auditoria (criado_em);

COMMIT;

