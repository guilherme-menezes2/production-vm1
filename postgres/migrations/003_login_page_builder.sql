BEGIN;

CREATE TABLE IF NOT EXISTS login_page_assets (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unidade_id BIGINT NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL,
  nome_original TEXT NOT NULL,
  filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  tamanho_bytes BIGINT NOT NULL,
  caminho_storage TEXT NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT login_page_assets_tipo_check CHECK (tipo IN ('logo', 'background', 'banner')),
  CONSTRAINT login_page_assets_tamanho_check CHECK (tamanho_bytes >= 0),
  CONSTRAINT login_page_assets_filename_unique UNIQUE (filename)
);

CREATE TABLE IF NOT EXISTS login_pages (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  unidade_id BIGINT NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  slug TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  titulo TEXT NOT NULL,
  subtitulo TEXT,
  texto_botao TEXT NOT NULL DEFAULT 'Acessar Wi-Fi',
  texto_privacidade TEXT,
  cor_primaria TEXT NOT NULL DEFAULT '#18B875',
  cor_fundo TEXT NOT NULL DEFAULT '#0F1115',
  cor_botao TEXT NOT NULL DEFAULT '#18B875',
  logo_asset_id BIGINT REFERENCES login_page_assets(id) ON DELETE SET NULL,
  background_asset_id BIGINT REFERENCES login_page_assets(id) ON DELETE SET NULL,
  banner_asset_id BIGINT REFERENCES login_page_assets(id) ON DELETE SET NULL,
  termo_titulo TEXT NOT NULL DEFAULT 'Termos de Uso do Wi-Fi',
  termo_texto TEXT NOT NULL,
  termo_versao TEXT NOT NULL DEFAULT 'dev-1',
  publicado_em TIMESTAMPTZ,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT login_pages_status_check CHECK (status IN ('draft', 'published')),
  CONSTRAINT login_pages_slug_check CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,80}$'),
  CONSTRAINT login_pages_cor_primaria_check CHECK (cor_primaria ~ '^#[0-9A-Fa-f]{6}$'),
  CONSTRAINT login_pages_cor_fundo_check CHECK (cor_fundo ~ '^#[0-9A-Fa-f]{6}$'),
  CONSTRAINT login_pages_cor_botao_check CHECK (cor_botao ~ '^#[0-9A-Fa-f]{6}$')
);

CREATE TABLE IF NOT EXISTS login_page_blocks (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  login_page_id BIGINT NOT NULL REFERENCES login_pages(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL,
  titulo TEXT,
  texto TEXT,
  ordem INTEGER NOT NULL DEFAULT 0,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT login_page_blocks_tipo_check CHECK (tipo IN ('beneficio', 'link_contato')),
  CONSTRAINT login_page_blocks_ordem_check CHECK (ordem >= 0)
);

CREATE INDEX IF NOT EXISTS idx_login_page_assets_unidade_id ON login_page_assets (unidade_id);
CREATE INDEX IF NOT EXISTS idx_login_page_assets_tipo ON login_page_assets (tipo);

CREATE INDEX IF NOT EXISTS idx_login_pages_unidade_id ON login_pages (unidade_id);
CREATE INDEX IF NOT EXISTS idx_login_pages_status ON login_pages (status);
CREATE INDEX IF NOT EXISTS idx_login_pages_slug ON login_pages (slug);
CREATE UNIQUE INDEX IF NOT EXISTS idx_login_pages_unidade_slug_status_unique
  ON login_pages (unidade_id, slug, status);

CREATE INDEX IF NOT EXISTS idx_login_page_blocks_login_page_id ON login_page_blocks (login_page_id);
CREATE INDEX IF NOT EXISTS idx_login_page_blocks_tipo ON login_page_blocks (tipo);
CREATE INDEX IF NOT EXISTS idx_login_page_blocks_ordem ON login_page_blocks (ordem);

COMMIT;
