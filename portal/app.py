import os
import re
import secrets
import string
import csv
import hmac
from pathlib import Path
from functools import wraps
from io import StringIO
from urllib.parse import urlencode
from uuid import uuid4

import psycopg
from flask import Flask, Response, abort, redirect, request, send_file, session
from psycopg.rows import dict_row


app = Flask(__name__)
app.secret_key = os.environ.get("PORTAL_SESSION_SECRET", "dev_example_portal_session_secret_change_me")

DATABASE_URL = os.environ.get("DATABASE_URL")
PORTAL_BASE_URL = os.environ.get("PORTAL_BASE_URL", "http://localhost:8080")
TERMO_VERSAO = os.environ.get("PORTAL_TERMO_VERSAO", "dev-1")
DEFAULT_CLIENTE_NOME = os.environ.get("PORTAL_DEFAULT_CLIENTE_NOME", "Cliente Academia Dev")
DEFAULT_CLIENTE_DOCUMENTO = os.environ.get("PORTAL_DEFAULT_CLIENTE_DOCUMENTO", "00000000000191")
DEFAULT_UNIDADE_NOME = os.environ.get("PORTAL_DEFAULT_UNIDADE_NOME", "Unidade Dev")
DEFAULT_UNIDADE_IDENTIFICADOR = os.environ.get("PORTAL_DEFAULT_UNIDADE_IDENTIFICADOR", "unidade-dev")
RATE_LIMIT = os.environ.get("PORTAL_RADIUS_RATE_LIMIT", "10M/5M")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin.local@example.test")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PORTAL_BRAND_NAME = os.environ.get("PORTAL_BRAND_NAME", "Wi-Fi Academia")
PORTAL_BRAND_TAGLINE = os.environ.get(
    "PORTAL_BRAND_TAGLINE",
    "Internet para treinar, trabalhar e se conectar com seguranca.",
)
PORTAL_SHOW_RADIUS_PASSWORD = os.environ.get("PORTAL_SHOW_RADIUS_PASSWORD", "true").lower() in (
    "1",
    "true",
    "yes",
    "sim",
)
PORTAL_UPLOAD_DIR = Path(os.environ.get("PORTAL_UPLOAD_DIR", "/app/data/uploads")).resolve()
PORTAL_MAX_IMAGE_BYTES = int(os.environ.get("PORTAL_MAX_IMAGE_BYTES", str(2 * 1024 * 1024)))
DEFAULT_TERMO_ATUALIZADO_EM = "16/06/2026"

ASSET_TYPES = {
    "logo": {
        "label": "Logo",
        "field": "logo_asset_id",
        "hint": "Marca exibida no topo do card de cadastro.",
    },
    "background": {
        "label": "Imagem de fundo",
        "field": "background_asset_id",
        "hint": "Imagem usada como fundo do preview da pagina publica.",
    },
    "banner": {
        "label": "Banner lateral",
        "field": "banner_asset_id",
        "hint": "Imagem de apoio exibida na area de boas-vindas.",
    },
}


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL nao definido")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def html_page(title, body, layout="public"):
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="/static/portal.css">
  <script src="/static/portal.js" defer></script>
</head>
<body class="{escape(layout)}-page">
{body}
</body>
</html>"""


def escape(value):
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def format_datetime_br(value):
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


def ensure_image_dimensions(width, height):
    if width <= 0 or height <= 0:
        raise ValueError("Imagem invalida. Dimensoes ausentes ou invalidas.")


def validate_png(content):
    if len(content) < 33:
        raise ValueError("Imagem PNG invalida.")
    ihdr_length = int.from_bytes(content[8:12], "big")
    if ihdr_length != 13 or content[12:16] != b"IHDR":
        raise ValueError("Imagem PNG invalida.")
    width = int.from_bytes(content[16:20], "big")
    height = int.from_bytes(content[20:24], "big")
    ensure_image_dimensions(width, height)

    position = 8
    while position + 12 <= len(content):
        chunk_length = int.from_bytes(content[position : position + 4], "big")
        chunk_type = content[position + 4 : position + 8]
        chunk_end = position + 8 + chunk_length + 4
        if chunk_end > len(content):
            raise ValueError("Imagem PNG invalida.")
        if chunk_type == b"IEND":
            if chunk_length != 0:
                raise ValueError("Imagem PNG invalida.")
            return
        position = chunk_end
    raise ValueError("Imagem PNG invalida.")


def validate_jpeg(content):
    if len(content) < 4 or not content.endswith(b"\xff\xd9"):
        raise ValueError("Imagem JPEG invalida.")
    position = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    standalone_markers = {0x01, *range(0xD0, 0xD9)}
    while position + 1 < len(content):
        if content[position] != 0xFF:
            position += 1
            continue
        while position < len(content) and content[position] == 0xFF:
            position += 1
        if position >= len(content):
            break
        marker = content[position]
        position += 1
        if marker in standalone_markers:
            continue
        if position + 2 > len(content):
            break
        segment_length = int.from_bytes(content[position : position + 2], "big")
        if segment_length < 2 or position + segment_length > len(content):
            raise ValueError("Imagem JPEG invalida.")
        if marker in sof_markers:
            if segment_length < 7:
                raise ValueError("Imagem JPEG invalida.")
            height = int.from_bytes(content[position + 3 : position + 5], "big")
            width = int.from_bytes(content[position + 5 : position + 7], "big")
            ensure_image_dimensions(width, height)
            return
        position += segment_length
    raise ValueError("Imagem JPEG invalida.")


def validate_webp(content):
    if len(content) < 20:
        raise ValueError("Imagem WebP invalida.")
    riff_size = int.from_bytes(content[4:8], "little")
    if riff_size + 8 > len(content):
        raise ValueError("Imagem WebP invalida.")
    chunk_type = content[12:16]
    if chunk_type == b"VP8X":
        if len(content) < 30:
            raise ValueError("Imagem WebP invalida.")
        width = 1 + int.from_bytes(content[24:27], "little")
        height = 1 + int.from_bytes(content[27:30], "little")
        ensure_image_dimensions(width, height)
        return
    if chunk_type == b"VP8L":
        if len(content) < 25 or content[20] != 0x2F:
            raise ValueError("Imagem WebP invalida.")
        bits = int.from_bytes(content[21:25], "little")
        width = 1 + (bits & 0x3FFF)
        height = 1 + ((bits >> 14) & 0x3FFF)
        ensure_image_dimensions(width, height)
        return
    if chunk_type == b"VP8 ":
        if b"\x9d\x01\x2a" not in content[16:64]:
            raise ValueError("Imagem WebP invalida.")
        return
    raise ValueError("Imagem WebP invalida.")


def detect_image_type(content):
    if content.startswith(b"\xff\xd8\xff"):
        validate_jpeg(content)
        return "image/jpeg", "jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        validate_png(content)
        return "image/png", "png"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        validate_webp(content)
        return "image/webp", "webp"
    raise ValueError("Arquivo invalido. Envie uma imagem JPEG, PNG ou WebP.")


def validate_asset_type(tipo):
    if tipo not in ASSET_TYPES:
        raise ValueError("Tipo de imagem invalido")
    return tipo


def read_validated_image(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("Selecione uma imagem para upload")
    content = file_storage.stream.read(PORTAL_MAX_IMAGE_BYTES + 1)
    if len(content) > PORTAL_MAX_IMAGE_BYTES:
        raise ValueError(f"Imagem excede o limite de {PORTAL_MAX_IMAGE_BYTES // 1024 // 1024} MB")
    if not content:
        raise ValueError("Arquivo vazio")
    mime_type, extension = detect_image_type(content)
    return content, mime_type, extension


def safe_original_filename(filename):
    name = os.path.basename(filename or "imagem")
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip()
    return name[:180] or "imagem"


def make_asset_filename(extension):
    PORTAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for _ in range(5):
        filename = f"{uuid4().hex}.{extension}"
        path = (PORTAL_UPLOAD_DIR / filename).resolve()
        if not path.exists():
            return filename, path
    raise RuntimeError("Nao foi possivel gerar nome seguro para upload")


def safe_storage_path(filename):
    path = (PORTAL_UPLOAD_DIR / filename).resolve()
    if not path.is_relative_to(PORTAL_UPLOAD_DIR):
        raise ValueError("Caminho de storage invalido")
    return path


def delete_storage_file(caminho_storage):
    if not caminho_storage:
        return
    try:
        path = safe_storage_path(os.path.basename(caminho_storage))
    except ValueError:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def asset_url(asset_id):
    return f"/login-page-assets/{int(asset_id)}" if asset_id else ""


def asset_is_published(cur, asset_id):
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM login_pages
          WHERE status = 'published'
            AND (
              logo_asset_id = %s
              OR background_asset_id = %s
              OR banner_asset_id = %s
            )
        ) AS public
        """,
        (asset_id, asset_id, asset_id),
    )
    return cur.fetchone()["public"]


def only_digits(value):
    return re.sub(r"\D", "", value or "")


def normalize_phone(value):
    digits = only_digits(value)
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) not in (10, 11):
        raise ValueError("Telefone deve ter 10 ou 11 digitos")
    return digits


def cpf_is_valid(cpf):
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    nums = [int(c) for c in cpf]
    total = sum(nums[i] * (10 - i) for i in range(9))
    digit = (total * 10) % 11
    if digit == 10:
        digit = 0
    if digit != nums[9]:
        return False
    total = sum(nums[i] * (11 - i) for i in range(10))
    digit = (total * 10) % 11
    if digit == 10:
        digit = 0
    return digit == nums[10]


def normalize_cpf(value):
    cpf = only_digits(value)
    if not cpf_is_valid(cpf):
        raise ValueError("CPF invalido")
    return cpf


def normalize_mac(value):
    raw = re.sub(r"[^0-9A-Fa-f]", "", value or "")
    if len(raw) != 12:
        raise ValueError("MAC deve ter 12 caracteres hexadecimais")
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2)).upper()


def normalize_ip(value):
    value = (value or "").strip()
    return value or None


def generate_password(length=14):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def username_for(cpf):
    return f"usr_{cpf}"


def default_login_page_data(unidade_id, status="published"):
    return {
        "unidade_id": unidade_id,
        "nome": "Pagina padrao local",
        "slug": DEFAULT_UNIDADE_IDENTIFICADOR,
        "status": status,
        "titulo": PORTAL_BRAND_NAME,
        "subtitulo": PORTAL_BRAND_TAGLINE,
        "texto_botao": "Acessar Wi-Fi",
        "texto_privacidade": "Seus dados sao usados apenas para controle de acesso, seguranca da rede e auditoria tecnica do hotspot.",
        "cor_primaria": "#18B875",
        "cor_fundo": "#0F1115",
        "cor_botao": "#18B875",
        "logo_asset_id": None,
        "background_asset_id": None,
        "banner_asset_id": None,
        "termo_titulo": "Termos de Uso do Wi-Fi",
        "termo_texto": "O acesso e destinado aos alunos, visitantes autorizados e equipe da academia durante a permanencia no local. Para liberar e auditar o acesso, o portal registra nome, telefone, CPF, endereco MAC, IP interno, horario de aceite e informacoes tecnicas da sessao. Este texto e uma versao de laboratorio e deve ser revisado antes de producao.",
        "termo_versao": TERMO_VERSAO,
    }


def ensure_default_unidade(cur):
    cur.execute(
        """
        INSERT INTO clientes (nome, documento, ativo)
        VALUES (%s, %s, TRUE)
        ON CONFLICT (documento) DO UPDATE
        SET nome = EXCLUDED.nome,
            ativo = TRUE
        RETURNING id
        """,
        (DEFAULT_CLIENTE_NOME, DEFAULT_CLIENTE_DOCUMENTO),
    )
    cliente_id = cur.fetchone()["id"]

    cur.execute(
        """
        INSERT INTO unidades (cliente_id, nome, identificador, ativo)
        VALUES (%s, %s, %s, TRUE)
        ON CONFLICT (cliente_id, identificador) DO UPDATE
        SET nome = EXCLUDED.nome,
            ativo = TRUE
        RETURNING id
        """,
        (cliente_id, DEFAULT_UNIDADE_NOME, DEFAULT_UNIDADE_IDENTIFICADOR),
    )
    return cur.fetchone()["id"]


def get_published_login_page(cur):
    cur.execute(
        """
        SELECT *
        FROM login_pages
        WHERE status = 'published'
        ORDER BY publicado_em DESC NULLS LAST, atualizado_em DESC, id DESC
        LIMIT 1
        """
    )
    return cur.fetchone()


def get_or_create_default_login_page(cur):
    unidade_id = ensure_default_unidade(cur)
    data = default_login_page_data(unidade_id, "published")
    cur.execute(
        """
        INSERT INTO login_pages (
          unidade_id,
          nome,
          slug,
          status,
          titulo,
          subtitulo,
          texto_botao,
          texto_privacidade,
          cor_primaria,
          cor_fundo,
          cor_botao,
          termo_titulo,
          termo_texto,
          termo_versao,
          publicado_em
        )
        VALUES (
          %s,
          %s,
          %s,
          'published',
          %s,
          %s,
          %s,
          %s,
          %s,
          %s,
          %s,
          %s,
          %s,
          %s,
          NOW()
        )
        ON CONFLICT (unidade_id, slug, status) DO UPDATE
        SET atualizado_em = login_pages.atualizado_em
        RETURNING *
        """,
        (
            data["unidade_id"],
            data["nome"],
            data["slug"],
            data["titulo"],
            data["subtitulo"],
            data["texto_botao"],
            data["texto_privacidade"],
            data["cor_primaria"],
            data["cor_fundo"],
            data["cor_botao"],
            data["termo_titulo"],
            data["termo_texto"],
            data["termo_versao"],
        ),
    )
    return cur.fetchone()


def ensure_default_blocks(cur, page_id):
    defaults = [
        ("beneficio", "Cadastro rapido", "Libere o acesso ao Wi-Fi em poucos segundos.", 1),
        ("beneficio", "Rede segura", "Controle de acesso e registros para seguranca da academia.", 2),
    ]
    for tipo, titulo, texto, ordem in defaults:
        cur.execute(
            """
            INSERT INTO login_page_blocks (login_page_id, tipo, titulo, texto, ordem, ativo)
            SELECT %s, %s, %s, %s, %s, TRUE
            WHERE NOT EXISTS (
              SELECT 1 FROM login_page_blocks
              WHERE login_page_id = %s
                AND tipo = %s
                AND ordem = %s
            )
            """,
            (page_id, tipo, titulo, texto, ordem, page_id, tipo, ordem),
        )


def get_or_create_draft_login_page(cur):
    published = get_published_login_page(cur) or get_or_create_default_login_page(cur)
    cur.execute(
        """
        SELECT *
        FROM login_pages
        WHERE unidade_id = %s
          AND slug = %s
          AND status = 'draft'
        LIMIT 1
        """,
        (published["unidade_id"], published["slug"]),
    )
    draft = cur.fetchone()
    if draft:
        return draft

    cur.execute(
        """
        INSERT INTO login_pages (
          unidade_id,
          nome,
          slug,
          status,
          titulo,
          subtitulo,
          texto_botao,
          texto_privacidade,
          cor_primaria,
          cor_fundo,
          cor_botao,
          logo_asset_id,
          background_asset_id,
          banner_asset_id,
          termo_titulo,
          termo_texto,
          termo_versao
        )
        VALUES (%s, %s, %s, 'draft', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            published["unidade_id"],
            published["nome"],
            published["slug"],
            published["titulo"],
            published["subtitulo"],
            published["texto_botao"],
            published["texto_privacidade"],
            published["cor_primaria"],
            published["cor_fundo"],
            published["cor_botao"],
            published["logo_asset_id"],
            published["background_asset_id"],
            published["banner_asset_id"],
            published["termo_titulo"],
            published["termo_texto"],
            published["termo_versao"],
        ),
    )
    draft = cur.fetchone()
    cur.execute(
        """
        INSERT INTO login_page_blocks (login_page_id, tipo, titulo, texto, ordem, ativo)
        SELECT %s, tipo, titulo, texto, ordem, ativo
        FROM login_page_blocks
        WHERE login_page_id = %s
        ORDER BY ordem, id
        """,
        (draft["id"], published["id"]),
    )
    ensure_default_blocks(cur, draft["id"])
    return draft


def get_login_page_assets(cur, page):
    asset_ids = [
        page.get("logo_asset_id"),
        page.get("background_asset_id"),
        page.get("banner_asset_id"),
    ]
    asset_ids = [asset_id for asset_id in asset_ids if asset_id]
    if not asset_ids:
        return {}
    cur.execute(
        """
        SELECT *
        FROM login_page_assets
        WHERE id = ANY(%s)
        """,
        (asset_ids,),
    )
    return {row["id"]: row for row in cur.fetchall()}


def get_login_page_blocks(cur, page_id):
    cur.execute(
        """
        SELECT *
        FROM login_page_blocks
        WHERE login_page_id = %s
          AND ativo = TRUE
        ORDER BY ordem, id
        """,
        (page_id,),
    )
    return cur.fetchall()


def update_login_page_content(cur, page_id, data):
    cur.execute(
        """
        UPDATE login_pages
        SET titulo = %s,
            subtitulo = %s,
            texto_botao = %s,
            texto_privacidade = %s,
            cor_primaria = %s,
            cor_fundo = %s,
            cor_botao = %s,
            termo_titulo = %s,
            termo_texto = %s,
            termo_versao = %s,
            atualizado_em = NOW()
        WHERE id = %s
        RETURNING *
        """,
        (
            data["titulo"],
            data["subtitulo"],
            data["texto_botao"],
            data["texto_privacidade"],
            data["cor_primaria"],
            data["cor_fundo"],
            data["cor_botao"],
            data["termo_titulo"],
            data["termo_texto"],
            data["termo_versao"],
            page_id,
        ),
    )
    return cur.fetchone()


def replace_benefit_blocks(cur, page_id, blocks):
    cur.execute(
        """
        DELETE FROM login_page_blocks
        WHERE login_page_id = %s
          AND tipo = 'beneficio'
        """,
        (page_id,),
    )
    for block in sorted(blocks, key=lambda item: (item["ordem"], item["titulo"])):
        cur.execute(
            """
            INSERT INTO login_page_blocks (login_page_id, tipo, titulo, texto, ordem, ativo)
            VALUES (%s, 'beneficio', %s, %s, %s, %s)
            """,
            (
                page_id,
                block["titulo"],
                block["texto"],
                block["ordem"],
                block["ativo"],
            ),
        )


def publish_draft_login_page(cur):
    draft = get_or_create_draft_login_page(cur)
    cur.execute(
        """
        UPDATE login_pages
        SET nome = %s,
            titulo = %s,
            subtitulo = %s,
            texto_botao = %s,
            texto_privacidade = %s,
            cor_primaria = %s,
            cor_fundo = %s,
            cor_botao = %s,
            logo_asset_id = %s,
            background_asset_id = %s,
            banner_asset_id = %s,
            termo_titulo = %s,
            termo_texto = %s,
            termo_versao = %s,
            publicado_em = NOW(),
            atualizado_em = NOW()
        WHERE unidade_id = %s
          AND slug = %s
          AND status = 'published'
        RETURNING *
        """,
        (
            draft["nome"],
            draft["titulo"],
            draft["subtitulo"],
            draft["texto_botao"],
            draft["texto_privacidade"],
            draft["cor_primaria"],
            draft["cor_fundo"],
            draft["cor_botao"],
            draft["logo_asset_id"],
            draft["background_asset_id"],
            draft["banner_asset_id"],
            draft["termo_titulo"],
            draft["termo_texto"],
            draft["termo_versao"],
            draft["unidade_id"],
            draft["slug"],
        ),
    )
    published = cur.fetchone()
    if not published:
        cur.execute(
            """
            INSERT INTO login_pages (
              unidade_id, nome, slug, status, titulo, subtitulo, texto_botao, texto_privacidade,
              cor_primaria, cor_fundo, cor_botao, logo_asset_id, background_asset_id, banner_asset_id,
              termo_titulo, termo_texto, termo_versao, publicado_em
            )
            VALUES (%s, %s, %s, 'published', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING *
            """,
            (
                draft["unidade_id"],
                draft["nome"],
                draft["slug"],
                draft["titulo"],
                draft["subtitulo"],
                draft["texto_botao"],
                draft["texto_privacidade"],
                draft["cor_primaria"],
                draft["cor_fundo"],
                draft["cor_botao"],
                draft["logo_asset_id"],
                draft["background_asset_id"],
                draft["banner_asset_id"],
                draft["termo_titulo"],
                draft["termo_texto"],
                draft["termo_versao"],
            ),
        )
        published = cur.fetchone()

    cur.execute("DELETE FROM login_page_blocks WHERE login_page_id = %s", (published["id"],))
    cur.execute(
        """
        INSERT INTO login_page_blocks (login_page_id, tipo, titulo, texto, ordem, ativo)
        SELECT %s, tipo, titulo, texto, ordem, ativo
        FROM login_page_blocks
        WHERE login_page_id = %s
        ORDER BY ordem, id
        """,
        (published["id"], draft["id"]),
    )
    return published


def asset_for_page(page, assets, tipo):
    asset_id = page.get(ASSET_TYPES[tipo]["field"])
    return assets.get(asset_id) if asset_id else None


def delete_asset_row_if_unreferenced(cur, asset_id):
    if not asset_id:
        return None
    cur.execute(
        """
        SELECT count(*) AS total
        FROM login_pages
        WHERE logo_asset_id = %s
           OR background_asset_id = %s
           OR banner_asset_id = %s
        """,
        (asset_id, asset_id, asset_id),
    )
    if cur.fetchone()["total"] != 0:
        return None
    cur.execute(
        """
        DELETE FROM login_page_assets
        WHERE id = %s
        RETURNING caminho_storage
        """,
        (asset_id,),
    )
    row = cur.fetchone()
    return row["caminho_storage"] if row else None


def create_or_reuse_user(cur, unidade_id, nome, telefone, cpf):
    cur.execute("SELECT * FROM usuarios WHERE cpf = %s LIMIT 1", (cpf,))
    user = cur.fetchone()
    if user:
        cur.execute(
            """
            UPDATE usuarios
            SET nome = %s,
                telefone = %s,
                ativo = TRUE,
                atualizado_em = NOW()
            WHERE id = %s
            RETURNING *
            """,
            (nome, telefone, user["id"]),
        )
        return cur.fetchone(), False

    username_radius = username_for(cpf)
    cur.execute(
        """
        INSERT INTO usuarios (unidade_id, nome, telefone, cpf, username_radius, ativo)
        VALUES (%s, %s, %s, %s, %s, TRUE)
        RETURNING *
        """,
        (unidade_id, nome, telefone, cpf, username_radius),
    )
    return cur.fetchone(), True


def create_or_update_device(cur, usuario_id, mac):
    cur.execute(
        """
        INSERT INTO dispositivos (usuario_id, mac, primeiro_acesso, ultimo_acesso)
        VALUES (%s, %s, NOW(), NOW())
        ON CONFLICT (usuario_id, mac) DO UPDATE
        SET ultimo_acesso = NOW()
        RETURNING *
        """,
        (usuario_id, mac),
    )
    return cur.fetchone()


def ensure_radius_credentials(cur, username_radius):
    cur.execute(
        """
        SELECT value
        FROM radcheck
        WHERE username = %s
          AND attribute = 'Cleartext-Password'
        ORDER BY id DESC
        LIMIT 1
        """,
        (username_radius,),
    )
    row = cur.fetchone()
    if row:
        password = row["value"]
    else:
        password = generate_password()
        cur.execute(
            """
            INSERT INTO radcheck (username, attribute, op, value)
            VALUES (%s, 'Cleartext-Password', ':=', %s)
            """,
            (username_radius, password),
        )

    cur.execute(
        """
        DELETE FROM radreply
        WHERE username = %s
          AND attribute = 'Mikrotik-Rate-Limit'
        """,
        (username_radius,),
    )
    cur.execute(
        """
        INSERT INTO radreply (username, attribute, op, value)
        VALUES (%s, 'Mikrotik-Rate-Limit', ':=', %s)
        """,
        (username_radius, RATE_LIMIT),
    )
    return password


def simulation_link(link_login, link_orig, username_radius, password):
    target = link_login or f"{PORTAL_BASE_URL.rstrip('/')}/login-simulado"
    params = {
        "username": username_radius,
        "password": password,
    }
    if link_orig:
        params["dst"] = link_orig
    separator = "&" if "?" in target else "?"
    return f"{target}{separator}{urlencode(params)}"


def admin_logged_in():
    return session.get("admin_logged_in") is True


def require_admin(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        if not admin_logged_in():
            return redirect("/admin")
        return handler(*args, **kwargs)

    return wrapper


def admin_nav():
    links = [
        ("/admin", "Dashboard"),
        ("/admin/page-builder", "Pagina login"),
        ("/admin/usuarios", "Usuarios"),
        ("/admin/dispositivos", "Dispositivos"),
        ("/admin/sessoes", "Sessoes"),
    ]
    items = []
    for href, label in links:
        is_active = request.path == href if href == "/admin" else request.path == href or request.path.startswith(f"{href}/")
        active = " is-active" if is_active else ""
        items.append(f'<a class="admin-nav__link{active}" href="{href}">{label}</a>')
    items.append('<a class="admin-nav__link admin-nav__link--exit" href="/admin/logout">Sair</a>')
    return f"""
<aside class="admin-sidebar">
  <div class="admin-brand">
    <span class="brand-mark">WA</span>
    <div>
      <strong>{escape(PORTAL_BRAND_NAME)}</strong>
      <small>Admin local</small>
    </div>
  </div>
  <nav class="admin-nav" aria-label="Navegacao administrativa">
    {''.join(items)}
  </nav>
</aside>
"""


def admin_shell(title, content):
    return html_page(
        title,
        f"""
<div class="admin-layout">
  {admin_nav()}
  <main class="admin-main">
    {content}
  </main>
</div>
""",
        layout="admin",
    )


def status_badge(value):
    if value is True:
        return '<span class="badge badge--success">Ativo</span>'
    if value is False:
        return '<span class="badge">Inativo</span>'
    return f'<span class="badge">{escape(value)}</span>'


def empty_row(colspan, message="Nenhum registro encontrado."):
    return f'<tr><td class="empty-cell" colspan="{colspan}">{escape(message)}</td></tr>'


def filter_form(action, include_period=False):
    cpf = escape(request.args.get("cpf", ""))
    telefone = escape(request.args.get("telefone", ""))
    mac = escape(request.args.get("mac", ""))
    ip = escape(request.args.get("ip", ""))
    start = escape(request.args.get("start", ""))
    end = escape(request.args.get("end", ""))
    period_fields = ""
    if include_period:
        period_fields = f"""
  <label>Inicio
    <input name="start" type="datetime-local" value="{start}">
  </label>
  <label>Fim
    <input name="end" type="datetime-local" value="{end}">
  </label>
"""
    return f"""
<form class="filter-card" method="get" action="{escape(action)}">
  <div class="filter-grid">
  <label>CPF
    <input name="cpf" value="{cpf}" inputmode="numeric" placeholder="Somente numeros">
  </label>
  <label>Telefone
    <input name="telefone" value="{telefone}" inputmode="tel" placeholder="DDD + numero">
  </label>
  <label>MAC
    <input name="mac" value="{mac}" placeholder="AA:BB:CC:DD:EE:FF">
  </label>
  <label>IP interno
    <input name="ip" value="{ip}" placeholder="10.120.0.10">
  </label>
{period_fields}
  </div>
  <div class="filter-actions">
    <button class="btn btn--primary" type="submit">Buscar</button>
    <a class="btn btn--ghost" href="{escape(action)}">Limpar</a>
  </div>
</form>
"""


def page_params():
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    page = max(page, 1)
    per_page = 25
    return page, per_page, (page - 1) * per_page


def current_filters():
    filters = {}
    cpf = only_digits(request.args.get("cpf", ""))
    telefone = only_digits(request.args.get("telefone", ""))
    mac = (request.args.get("mac") or "").strip()
    ip = (request.args.get("ip") or "").strip()
    if cpf:
        filters["cpf"] = cpf
    if telefone:
        filters["telefone"] = telefone
    if mac:
        try:
            filters["mac"] = normalize_mac(mac)
        except ValueError:
            filters["mac"] = mac.upper()
    if ip:
        filters["ip"] = ip
    return filters


def append_user_filters(where, params, filters, user_alias="u"):
    if filters.get("cpf"):
        where.append(f"{user_alias}.cpf = %s")
        params.append(filters["cpf"])
    if filters.get("telefone"):
        where.append(f"{user_alias}.telefone = %s")
        params.append(filters["telefone"])
    if filters.get("mac"):
        where.append(
            f"""EXISTS (
              SELECT 1 FROM dispositivos df
              WHERE df.usuario_id = {user_alias}.id
                AND df.mac = %s
            )"""
        )
        params.append(filters["mac"])
    if filters.get("ip"):
        where.append(
            f"""(
              EXISTS (
                SELECT 1 FROM login_auditoria laf
                WHERE laf.usuario_id = {user_alias}.id
                  AND laf.ip_interno = %s
              )
              OR EXISTS (
                SELECT 1 FROM radacct raf
                WHERE raf.username = {user_alias}.username_radius
                  AND raf.framedipaddress = %s
              )
            )"""
        )
        params.extend([filters["ip"], filters["ip"]])


def where_sql(where):
    return " WHERE " + " AND ".join(where) if where else ""


def query_string_with_page(page):
    args = request.args.to_dict()
    args["page"] = str(page)
    return urlencode(args)


def pagination_links(page, has_next):
    links = []
    if page > 1:
        links.append(f'<a class="btn btn--ghost" href="?{escape(query_string_with_page(page - 1))}">Anterior</a>')
    if has_next:
        links.append(f'<a class="btn btn--ghost" href="?{escape(query_string_with_page(page + 1))}">Proxima</a>')
    return '<div class="pagination">' + " ".join(links) + "</div>" if links else ""


def date_filter(column, where, params):
    start = request.args.get("start") or ""
    end = request.args.get("end") or ""
    if start:
        where.append(f"{column} >= %s")
        params.append(start.replace("T", " "))
    if end:
        where.append(f"{column} <= %s")
        params.append(end.replace("T", " "))


def builder_message():
    messages = {
        "upload": ("Imagem enviada com sucesso.", "success"),
        "remove": ("Imagem removida com sucesso.", "success"),
        "draft": ("Rascunho salvo com sucesso.", "success"),
        "publish": ("Pagina publicada com sucesso.", "success"),
    }
    error = request.args.get("erro")
    if error:
        return f'<div class="alert alert--error">{escape(error)}</div>'
    ok = request.args.get("ok")
    if ok in messages:
        text, kind = messages[ok]
        return f'<div class="alert alert--{kind}">{escape(text)}</div>'
    return ""


def clean_text_field(name, *, required=False, max_length=5000):
    value = (request.form.get(name) or "").strip()
    if required and not value:
        raise ValueError(f"Campo obrigatorio: {name}")
    if len(value) > max_length:
        raise ValueError(f"Campo muito longo: {name}")
    return value


def clean_color_field(name):
    value = (request.form.get(name) or "").strip()
    if not re.match(r"^#[0-9A-Fa-f]{6}$", value):
        raise ValueError(f"Cor invalida em {name}. Use #RRGGBB.")
    return value.upper()


def clean_int_field(name, default=0):
    value = (request.form.get(name) or "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"Ordem invalida em {name}") from exc
    if parsed < 0:
        raise ValueError(f"Ordem nao pode ser negativa em {name}")
    return parsed


def collect_builder_form():
    data = {
        "titulo": clean_text_field("titulo", required=True, max_length=140),
        "subtitulo": clean_text_field("subtitulo", max_length=280),
        "texto_botao": clean_text_field("texto_botao", required=True, max_length=80),
        "texto_privacidade": clean_text_field("texto_privacidade", max_length=500),
        "cor_primaria": clean_color_field("cor_primaria"),
        "cor_fundo": clean_color_field("cor_fundo"),
        "cor_botao": clean_color_field("cor_botao"),
        "termo_titulo": clean_text_field("termo_titulo", required=True, max_length=160),
        "termo_texto": clean_text_field("termo_texto", required=True, max_length=8000),
        "termo_versao": clean_text_field("termo_versao", required=True, max_length=40),
    }
    blocks = []
    for index in range(1, 6):
        titulo = clean_text_field(f"beneficio_{index}_titulo", max_length=100)
        texto = clean_text_field(f"beneficio_{index}_texto", max_length=220)
        ordem = clean_int_field(f"beneficio_{index}_ordem", index)
        ativo = request.form.get(f"beneficio_{index}_ativo") == "1"
        if titulo or texto:
            blocks.append(
                {
                    "tipo": "beneficio",
                    "titulo": titulo,
                    "texto": texto,
                    "ordem": ordem,
                    "ativo": ativo,
                }
            )
    return data, blocks


def render_builder_form(page, blocks):
    benefit_blocks = [block for block in blocks if block["tipo"] == "beneficio"]
    rows = []
    for index in range(1, 6):
        block = benefit_blocks[index - 1] if index <= len(benefit_blocks) else {}
        checked = " checked" if block.get("ativo", True) else ""
        rows.append(
            f"""
<div class="builder-block-row">
  <label>Titulo
    <input name="beneficio_{index}_titulo" value="{escape(block.get("titulo", ""))}" maxlength="100">
  </label>
  <label>Texto
    <input name="beneficio_{index}_texto" value="{escape(block.get("texto", ""))}" maxlength="220">
  </label>
  <label>Ordem
    <input name="beneficio_{index}_ordem" type="number" min="0" value="{escape(block.get("ordem", index))}">
  </label>
  <label class="checkbox-line builder-checkbox">
    <input type="checkbox" name="beneficio_{index}_ativo" value="1"{checked}>
    <span>Ativo</span>
  </label>
</div>
"""
        )
    return f"""
<form class="builder-form" method="post" action="/admin/page-builder/save">
  <div class="form-grid form-grid--two">
    <label>Titulo
      <input name="titulo" required maxlength="140" value="{escape(page["titulo"])}">
    </label>
    <label>Subtitulo
      <input name="subtitulo" maxlength="280" value="{escape(page["subtitulo"])}">
    </label>
    <label>Texto do botao
      <input name="texto_botao" required maxlength="80" value="{escape(page["texto_botao"])}">
    </label>
    <label>Texto de privacidade
      <input name="texto_privacidade" maxlength="500" value="{escape(page["texto_privacidade"])}">
    </label>
  </div>
  <div class="form-grid form-grid--three">
    <label>Cor principal
      <input name="cor_primaria" type="color" value="{escape(page["cor_primaria"])}">
    </label>
    <label>Cor de fundo
      <input name="cor_fundo" type="color" value="{escape(page["cor_fundo"])}">
    </label>
    <label>Cor dos botoes
      <input name="cor_botao" type="color" value="{escape(page["cor_botao"])}">
    </label>
  </div>
  <div class="form-grid">
    <label>Titulo dos termos
      <input name="termo_titulo" required maxlength="160" value="{escape(page["termo_titulo"])}">
    </label>
    <label>Versao do termo
      <input name="termo_versao" required maxlength="40" value="{escape(page["termo_versao"])}">
    </label>
    <label>Texto dos termos
      <textarea name="termo_texto" required maxlength="8000" rows="8">{escape(page["termo_texto"])}</textarea>
    </label>
  </div>
  <div class="builder-blocks">
    <h3>Blocos de beneficios</h3>
    <p>Preencha ate 5 beneficios. A exibicao usa o campo ordem em ordem crescente.</p>
    {''.join(rows)}
  </div>
  <div class="filter-actions">
    <button class="btn btn--primary" type="submit">Salvar rascunho</button>
    <button class="btn btn--ghost" type="submit" formaction="/admin/page-builder/publish">Publicar pagina</button>
    <a class="btn btn--ghost" href="/admin/page-builder/preview?status=draft">Preview rascunho</a>
    <a class="btn btn--ghost" href="/admin/page-builder/preview?status=published">Preview publicado</a>
  </div>
</form>
"""


def render_asset_card(page, assets, tipo):
    info = ASSET_TYPES[tipo]
    asset = asset_for_page(page, assets, tipo)
    preview = '<div class="asset-preview asset-preview--empty">Sem imagem</div>'
    remove_form = ""
    if asset:
        preview = f"""
<div class="asset-preview">
  <img src="{escape(asset_url(asset["id"]))}" alt="{escape(info["label"])} atual">
</div>
<p class="asset-meta">{escape(asset["nome_original"])} | {escape(asset["mime_type"])} | {escape(asset["tamanho_bytes"])} bytes</p>
"""
        remove_form = f"""
<form method="post" action="/admin/page-builder/assets/remove">
  <input type="hidden" name="tipo" value="{escape(tipo)}">
  <button class="btn btn--ghost" type="submit">Remover</button>
</form>
"""
    return f"""
<article class="asset-card">
  <div class="asset-card__header">
    <div>
      <h3>{escape(info["label"])}</h3>
      <p>{escape(info["hint"])}</p>
    </div>
  </div>
  {preview}
  <form method="post" action="/admin/page-builder/assets" enctype="multipart/form-data">
    <input type="hidden" name="tipo" value="{escape(tipo)}">
    <label>Enviar {escape(info["label"]).lower()}
      <input name="imagem" type="file" accept="image/jpeg,image/png,image/webp" required>
    </label>
    <button class="btn btn--primary" type="submit">Salvar imagem</button>
  </form>
  {remove_form}
</article>
"""


def render_login_page_content(page, assets, blocks, hotspot_params, preview_status=None):
    title = page["titulo"] if page else PORTAL_BRAND_NAME
    subtitle = page["subtitulo"] if page else PORTAL_BRAND_TAGLINE
    button_text = page["texto_botao"] if page else "Acessar Wi-Fi"
    privacy_text = (
        page["texto_privacidade"]
        if page
        else "Seus dados sao usados apenas para controle de acesso, seguranca da rede e auditoria tecnica do hotspot."
    )
    color_style = ""
    background_style = ""
    logo_html = '<span class="brand-mark">WA</span>'
    banner_html = ""
    benefits_html = "<span>Cadastro rapido</span><span>Controle de acesso</span><span>Ambiente local</span>"
    if page:
        color_style = f"--accent: {escape(page['cor_botao'])}; --accent-dark: {escape(page['cor_primaria'])};"
        background_style = f"background-color: {escape(page['cor_fundo'])};"
        logo = asset_for_page(page, assets, "logo")
        background = asset_for_page(page, assets, "background")
        banner = asset_for_page(page, assets, "banner")
        if logo:
            logo_html = f'<img class="login-logo" src="{escape(asset_url(logo["id"]))}" alt="Logo">'
        if background:
            background_style += f" background-image: linear-gradient(135deg, rgba(15, 17, 21, 0.88), rgba(35, 39, 49, 0.84)), url('{escape(asset_url(background['id']))}'); background-size: cover; background-position: center;"
        if banner:
            banner_html = f'<img class="builder-banner" src="{escape(asset_url(banner["id"]))}" alt="Banner lateral">'
        benefit_blocks = [block for block in blocks if block["tipo"] == "beneficio"]
        if benefit_blocks:
            benefits_html = "".join(
                f"<span>{escape(block['titulo'] or block['texto'])}</span>" for block in benefit_blocks
            )
        else:
            benefits_html = ""
    hero_list_html = f"""
    <div class="hero-list">
      {benefits_html}
    </div>
""" if benefits_html else ""

    preview = preview_status in ("draft", "published")
    form_action = "/admin/page-builder/preview-submit" if preview else "/cadastro"
    preview_hidden = ""
    preview_notice = ""
    name_value = ""
    phone_value = ""
    cpf_value = ""
    checked = ""
    if preview:
        status_label = "rascunho" if preview_status == "draft" else "publicado"
        preview_hidden = f'<input type="hidden" name="preview_status" value="{escape(preview_status)}">'
        preview_notice = f"""
    <div class="preview-warning" role="status">
      <strong>Modo preview</strong>
      <span>Visualizando a pagina em modo {escape(status_label)}. Este formulario nao cria usuario nem autentica no RADIUS.</span>
    </div>
"""
        name_value = ' value="Aluno Preview"'
        phone_value = ' value="85900000000"'
        cpf_value = ' value="123.456.789-09"'
        checked = " checked"

    mac = hotspot_params.get("mac", "")
    ip = hotspot_params.get("ip", "")
    link_login = hotspot_params.get("link_login", "")
    link_orig = hotspot_params.get("link_orig", "")
    nas_ip = hotspot_params.get("nas_ip", "")

    return f"""
<main class="public-shell" style="{color_style} {background_style}">
  <section class="public-hero" aria-label="Boas-vindas">
    <div class="brand-pill">Acesso Wi-Fi</div>
    <h1>{escape(title)}</h1>
    <p>{escape(subtitle)}</p>
    {hero_list_html}
    {banner_html}
  </section>

  <section class="auth-card" aria-label="Formulario de acesso Wi-Fi">
    <div class="card-header">
      {logo_html}
      <div>
        <h2>Conecte-se</h2>
        <p>{escape(subtitle)}</p>
      </div>
    </div>
{preview_notice}
<form method="post" action="{escape(form_action)}">
  {preview_hidden}
  <input type="hidden" name="mac" value="{escape(mac)}">
  <input type="hidden" name="ip" value="{escape(ip)}">
  <input type="hidden" name="link_login" value="{escape(link_login)}">
  <input type="hidden" name="link_orig" value="{escape(link_orig)}">
  <input type="hidden" name="nas_ip" value="{escape(nas_ip)}">

  <label>Nome completo
    <input name="nome" required autocomplete="name" placeholder="Seu nome"{name_value}>
  </label>
  <label>Telefone
    <input name="telefone" required inputmode="tel" placeholder="DDD + numero"{phone_value}>
  </label>
  <label>CPF
    <input name="cpf" required inputmode="numeric" autocomplete="off" maxlength="14" placeholder="Somente numeros" data-validate-cpf aria-describedby="cpf-error"{cpf_value}>
    <span class="field-error" id="cpf-error" data-cpf-error hidden>Informe um CPF valido.</span>
  </label>
  <label class="checkbox-line">
    <input type="checkbox" name="aceite_termo" value="1" required{checked}>
    <span>Aceito os <a href="/termos" target="_blank">termos de uso</a>.</span>
  </label>
  <button class="btn btn--primary btn--wide" type="submit">{escape(button_text)}</button>
</form>
    <p class="privacy-note">{escape(privacy_text)}</p>

    <details class="debug-panel"{" open" if preview else ""}>
      <summary>Dados tecnicos do Hotspot local</summary>
      <dl>
        <div><dt>MAC</dt><dd><code>{escape(mac)}</code></dd></div>
        <div><dt>IP</dt><dd><code>{escape(ip)}</code></dd></div>
        <div><dt>NAS IP</dt><dd><code>{escape(nas_ip)}</code></dd></div>
      </dl>
    </details>
  </section>
</main>
"""


def render_login_page_preview(page, assets, blocks, preview_status="draft"):
    hotspot_params = {
        "mac": "AA:BB:CC:DD:EE:FF",
        "ip": "10.120.0.10",
        "link_login": "http://10.120.0.1/login",
        "link_orig": "http://example.com",
        "nas_ip": "10.120.0.1",
    }
    return f"""
<div class="page-preview-frame">
  {render_login_page_content(page, assets, blocks, hotspot_params, preview_status)}
</div>
"""


@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "database": "ok"}
    except Exception:
        return {"status": "error", "database": "error"}, 500


@app.get("/")
def index():
    return redirect("/login")


@app.get("/login")
def login():
    page = None
    assets = {}
    blocks = []
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            page = get_published_login_page(cur)
            if page:
                assets = get_login_page_assets(cur, page)
                blocks = get_login_page_blocks(cur, page["id"])
    except Exception:
        page = None

    hotspot_params = {
        "mac": request.args.get("mac", ""),
        "ip": request.args.get("ip", ""),
        "link_login": request.args.get("link_login", ""),
        "link_orig": request.args.get("link_orig", ""),
        "nas_ip": request.args.get("nas_ip", ""),
    }
    body = render_login_page_content(page, assets, blocks, hotspot_params)
    return html_page("Login Hotspot Local", body)


@app.post("/cadastro")
def cadastro():
    try:
        nome = (request.form.get("nome") or "").strip()
        if len(nome) < 3:
            raise ValueError("Nome deve ter pelo menos 3 caracteres")
        telefone = normalize_phone(request.form.get("telefone"))
        cpf = normalize_cpf(request.form.get("cpf"))
        mac = normalize_mac(request.form.get("mac"))
        ip_interno = normalize_ip(request.form.get("ip"))
        nas_ip = normalize_ip(request.form.get("nas_ip"))
        link_login = request.form.get("link_login") or ""
        link_orig = request.form.get("link_orig") or ""
        if request.form.get("aceite_termo") != "1":
            raise ValueError("Aceite dos termos e obrigatorio")
    except ValueError as exc:
        body = f"""
<main class="message-shell">
  <section class="message-card message-card--error">
    <span class="message-icon">!</span>
    <h1>Confira os dados</h1>
    <p>{escape(exc)}</p>
    <a class="btn btn--primary" href="/login">Voltar ao login</a>
  </section>
</main>
"""
        return html_page("Erro no cadastro", body), 400

    user_agent = request.headers.get("User-Agent")

    try:
        with get_conn() as conn:
            with conn.transaction():
                cur = conn.cursor()
                unidade_id = ensure_default_unidade(cur)
                page = get_published_login_page(cur)
                termo_versao = page["termo_versao"] if page else TERMO_VERSAO
                usuario, criado = create_or_reuse_user(cur, unidade_id, nome, telefone, cpf)
                create_or_update_device(cur, usuario["id"], mac)
                cur.execute(
                    """
                    INSERT INTO termos_aceite
                      (usuario_id, versao_termo, ip_aceite, mac_aceite, user_agent)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (usuario["id"], termo_versao, ip_interno, mac, user_agent),
                )
                password = ensure_radius_credentials(cur, usuario["username_radius"])
                cur.execute(
                    """
                    INSERT INTO login_auditoria
                      (usuario_id, username_radius, mac, ip_interno, nas_ip, resultado)
                    VALUES (%s, %s, %s, %s, %s, 'cadastro_local')
                    """,
                    (usuario["id"], usuario["username_radius"], mac, ip_interno, nas_ip),
                )
    except Exception as exc:
        body = f"""
<main class="message-shell">
  <section class="message-card message-card--error">
    <span class="message-icon">!</span>
    <h1>Nao foi possivel concluir</h1>
    <p>Falha ao processar cadastro: {escape(exc)}</p>
    <a class="btn btn--primary" href="/login">Tentar novamente</a>
  </section>
</main>
"""
        return html_page("Erro no cadastro", body), 500

    login_url = simulation_link(link_login, link_orig, usuario["username_radius"], password)
    status = "criado" if criado else "reutilizado"
    debug_credentials = ""
    if PORTAL_SHOW_RADIUS_PASSWORD:
        debug_credentials = f"""
      <div class="debug-credentials">
        <p class="debug-title">Debug local</p>
        <ul>
          <li>username_radius: <code>{escape(usuario["username_radius"])}</code></li>
          <li>password gerado: <code>{escape(password)}</code></li>
          <li>limite RADIUS: <code>Mikrotik-Rate-Limit = {escape(RATE_LIMIT)}</code></li>
        </ul>
        <p>A senha aparece na tela apenas para debug local. Remover isso em producao.</p>
      </div>
"""
    body = f"""
<main class="message-shell">
  <section class="message-card message-card--success">
    <span class="message-icon">OK</span>
    <p class="eyebrow">Usuario {escape(status)}</p>
    <h1>Acesso liberado</h1>
    <p>Seu cadastro foi concluido e o acesso Wi-Fi esta sendo liberado.</p>
    <a class="btn btn--primary btn--wide" href="{escape(login_url)}">Continuar para o Wi-Fi</a>
    {debug_credentials}
  </section>
</main>
"""
    return html_page("Cadastro concluido", body)


@app.get("/termos")
def termos():
    page = None
    try:
        with get_conn() as conn:
            page = get_published_login_page(conn.cursor())
    except Exception:
        page = None
    termo_titulo = page["termo_titulo"] if page else "Termos de Uso do Wi-Fi"
    termo_texto = page["termo_texto"] if page else "O acesso e destinado aos alunos, visitantes autorizados e equipe da academia durante a permanencia no local."
    termo_versao = page["termo_versao"] if page else TERMO_VERSAO
    termo_data = (
        format_datetime_br(page.get("publicado_em") or page.get("atualizado_em"))
        if page
        else DEFAULT_TERMO_ATUALIZADO_EM
    )
    paragraphs = "".join(
        f"<p>{escape(part.strip())}</p>" for part in termo_texto.splitlines() if part.strip()
    )
    if not paragraphs:
        paragraphs = f"<p>{escape(termo_texto)}</p>"
    body = f"""
<main class="terms-shell">
  <article class="terms-card">
    <p class="eyebrow">Versao {escape(termo_versao)} | Publicado/atualizado em {escape(termo_data)}</p>
    <h1>{escape(termo_titulo)}</h1>
    <section>
      {paragraphs}
    </section>
    <a class="btn btn--primary" href="/login">Voltar ao login</a>
  </article>
</main>
"""
    return html_page("Termos de Uso", body)


@app.get("/login-simulado")
def login_simulado():
    username = request.args.get("username", "")
    body = f"""
<main class="message-shell">
  <section class="message-card">
    <span class="message-icon">Wi-Fi</span>
    <h1>Login simulado</h1>
    <p>Esta pagina representa o ponto em que o MikroTik receberia as credenciais no laboratorio local.</p>
    <p>Usuario RADIUS: <code>{escape(username)}</code></p>
    <p class="notice">A senha nao e enviada na URL para evitar registro em logs.</p>
  </section>
</main>
"""
    return html_page("Login Simulado", body)


@app.get("/login-page-assets/<int:asset_id>")
def login_page_asset(asset_id):
    with get_conn() as conn:
        cur = conn.cursor()
        asset = cur.execute(
            """
            SELECT id, filename, mime_type, caminho_storage
            FROM login_page_assets
            WHERE id = %s
            """,
            (asset_id,),
        ).fetchone()
        if asset and not admin_logged_in() and not asset_is_published(cur, asset_id):
            abort(404)
    if not asset:
        abort(404)
    try:
        path = safe_storage_path(os.path.basename(asset["caminho_storage"]))
    except ValueError:
        abort(404)
    if not path.exists():
        abort(404)
    response = send_file(
        path,
        mimetype=asset["mime_type"],
        download_name=asset["filename"],
        conditional=True,
        max_age=3600,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/admin", methods=["GET"])
def admin():
    if not admin_logged_in():
        error = request.args.get("erro")
        error_html = '<div class="alert alert--error">Login administrativo invalido.</div>' if error else ""
        body = f"""
<main class="admin-login-shell">
  <section class="admin-login-card">
    <div class="card-header">
      <span class="brand-mark">WA</span>
      <div>
        <h1>Admin Local</h1>
        <p>Gestao de usuarios, dispositivos e sessoes do hotspot.</p>
      </div>
    </div>
    {error_html}
    <form method="post" action="/admin/login">
      <label>Email
        <input name="email" type="email" required value="{escape(ADMIN_EMAIL)}">
      </label>
      <label>Senha
        <input name="password" type="password" required>
      </label>
      <button class="btn btn--primary btn--wide" type="submit">Entrar</button>
    </form>
    <p class="notice">Ambiente local. Em producao, use senha forte e segredo de sessao proprio.</p>
  </section>
</main>
"""
        return html_page("Admin Login", body, layout="admin")

    with get_conn() as conn:
        resumo = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM usuarios) AS usuarios,
              (SELECT count(*) FROM dispositivos) AS dispositivos,
              (SELECT count(*) FROM radacct) AS sessoes,
              (SELECT count(*) FROM radacct WHERE acctstarttime IS NOT NULL AND acctstoptime IS NULL) AS sessoes_abertas,
              (SELECT count(*) FROM usuarios WHERE criado_em::date = CURRENT_DATE) AS cadastros_hoje,
              (SELECT count(*) FROM radacct WHERE acctstarttime >= NOW() - INTERVAL '24 hours') AS sessoes_recentes
            """
        ).fetchone()

    content = f"""
<header class="page-header">
  <div>
    <p class="eyebrow">Painel local</p>
    <h1>Dashboard</h1>
  </div>
  <a class="btn btn--ghost" href="/login">Ver portal publico</a>
</header>

<section class="metric-grid" aria-label="Resumo do hotspot">
  <article class="metric-card"><span>Total de usuarios</span><strong>{escape(resumo["usuarios"])}</strong></article>
  <article class="metric-card"><span>Total de dispositivos</span><strong>{escape(resumo["dispositivos"])}</strong></article>
  <article class="metric-card"><span>Sessoes recentes</span><strong>{escape(resumo["sessoes_recentes"])}</strong></article>
  <article class="metric-card"><span>Sessoes abertas</span><strong>{escape(resumo["sessoes_abertas"])}</strong></article>
  <article class="metric-card"><span>Cadastros do dia</span><strong>{escape(resumo["cadastros_hoje"])}</strong></article>
</section>

<section class="panel">
  <div class="panel-heading">
    <div>
      <h2>Busca rapida</h2>
      <p>Consulte sessoes por CPF, telefone, MAC, IP interno ou periodo.</p>
    </div>
  </div>
  {filter_form("/admin/sessoes", include_period=True)}
</section>
"""
    return admin_shell("Admin Local", content)


@app.post("/admin/login")
def admin_login():
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    email_ok = hmac.compare_digest(email, ADMIN_EMAIL)
    password_ok = bool(ADMIN_PASSWORD) and hmac.compare_digest(password, ADMIN_PASSWORD)
    if email_ok and password_ok:
        session.clear()
        session["admin_logged_in"] = True
        session["admin_email"] = ADMIN_EMAIL
        return redirect("/admin")
    return redirect("/admin?erro=1")


@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin")


@app.get("/admin/page-builder")
@require_admin
def admin_page_builder():
    with get_conn() as conn:
        with conn.transaction():
            cur = conn.cursor()
            page = get_or_create_draft_login_page(cur)
            assets = get_login_page_assets(cur, page)
            blocks = get_login_page_blocks(cur, page["id"])

    asset_cards = "".join(render_asset_card(page, assets, tipo) for tipo in ASSET_TYPES)
    preview = render_login_page_preview(page, assets, blocks)
    form = render_builder_form(page, blocks)
    content = f"""
<header class="page-header">
  <div>
    <p class="eyebrow">Personalizacao</p>
    <h1>Pagina de login</h1>
  </div>
  <div class="filter-actions">
    <a class="btn btn--primary" href="/admin/page-builder/preview?status=draft">Preview rascunho</a>
    <a class="btn btn--ghost" href="/admin/page-builder/preview?status=published">Preview publicado</a>
  </div>
</header>
{builder_message()}
<section class="panel">
  <div class="panel-heading">
    <div>
      <h2>Conteudo do rascunho</h2>
      <p>Altere textos, cores, termos e beneficios. O login publico so muda depois de publicar.</p>
    </div>
  </div>
  {form}
</section>
<section class="panel">
  <div class="panel-heading">
    <div>
      <h2>Imagens da pagina publica</h2>
      <p>Envie JPEG, PNG ou WebP. Limite por arquivo: {PORTAL_MAX_IMAGE_BYTES // 1024 // 1024} MB.</p>
    </div>
  </div>
  <div class="asset-grid">
    {asset_cards}
  </div>
</section>
<section class="panel">
  <div class="panel-heading">
    <div>
      <h2>Preview rapido</h2>
      <p>As imagens abaixo sao carregadas pelo ID do asset, sem expor caminho interno do servidor.</p>
    </div>
  </div>
  {preview}
</section>
"""
    return admin_shell("Pagina de login", content)


@app.post("/admin/page-builder/assets")
@require_admin
def admin_page_builder_upload_asset():
    new_path = None
    old_path = None
    try:
        tipo = validate_asset_type(request.form.get("tipo", ""))
        content, mime_type, extension = read_validated_image(request.files.get("imagem"))
        filename, new_path = make_asset_filename(extension)
        new_path.write_bytes(content)
        caminho_storage = str(new_path)
        original_name = safe_original_filename(request.files["imagem"].filename)

        with get_conn() as conn:
            with conn.transaction():
                cur = conn.cursor()
                page = get_or_create_draft_login_page(cur)
                field = ASSET_TYPES[tipo]["field"]
                old_asset_id = page.get(field)
                cur.execute(
                    """
                    INSERT INTO login_page_assets
                      (unidade_id, tipo, nome_original, filename, mime_type, tamanho_bytes, caminho_storage)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        page["unidade_id"],
                        tipo,
                        original_name,
                        filename,
                        mime_type,
                        len(content),
                        caminho_storage,
                    ),
                )
                asset_id = cur.fetchone()["id"]
                cur.execute(
                    f"""
                    UPDATE login_pages
                    SET {field} = %s,
                        atualizado_em = NOW()
                    WHERE id = %s
                    """,
                    (asset_id, page["id"]),
                )
                old_path = delete_asset_row_if_unreferenced(cur, old_asset_id)
    except Exception as exc:
        if new_path:
            delete_storage_file(str(new_path))
        return redirect(f"/admin/page-builder?{urlencode({'erro': str(exc)})}")

    delete_storage_file(old_path)
    return redirect("/admin/page-builder?ok=upload")


@app.post("/admin/page-builder/assets/remove")
@require_admin
def admin_page_builder_remove_asset():
    old_path = None
    try:
        tipo = validate_asset_type(request.form.get("tipo", ""))
        with get_conn() as conn:
            with conn.transaction():
                cur = conn.cursor()
                page = get_or_create_draft_login_page(cur)
                field = ASSET_TYPES[tipo]["field"]
                old_asset_id = page.get(field)
                cur.execute(
                    f"""
                    UPDATE login_pages
                    SET {field} = NULL,
                        atualizado_em = NOW()
                    WHERE id = %s
                    """,
                    (page["id"],),
                )
                old_path = delete_asset_row_if_unreferenced(cur, old_asset_id)
    except Exception as exc:
        return redirect(f"/admin/page-builder?{urlencode({'erro': str(exc)})}")

    delete_storage_file(old_path)
    return redirect("/admin/page-builder?ok=remove")


@app.get("/admin/page-builder/preview")
@require_admin
def admin_page_builder_preview():
    preview_status = request.args.get("status", "draft")
    if preview_status not in ("draft", "published"):
        preview_status = "draft"
    with get_conn() as conn:
        with conn.transaction():
            cur = conn.cursor()
            if preview_status == "published":
                page = get_published_login_page(cur)
                if page:
                    assets = get_login_page_assets(cur, page)
                    blocks = get_login_page_blocks(cur, page["id"])
                else:
                    page = default_login_page_data(None, "published")
                    assets = {}
                    blocks = []
            else:
                page = get_or_create_draft_login_page(cur)
                assets = get_login_page_assets(cur, page)
                blocks = get_login_page_blocks(cur, page["id"])

    status_label = "rascunho" if preview_status == "draft" else "publicada"
    ok_html = ""
    if request.args.get("ok") == "preview":
        ok_html = '<div class="alert alert--success">Clique recebido em modo preview. Nenhum usuario, termo ou credencial RADIUS foi criado.</div>'
    content = f"""
<header class="page-header">
  <div>
    <p class="eyebrow">Preview</p>
    <h1>Pagina publica de login ({escape(status_label)})</h1>
  </div>
  <div class="filter-actions">
    <a class="btn btn--ghost" href="/admin/page-builder">Voltar para edicao</a>
    <a class="btn btn--ghost" href="/admin/page-builder/preview?status=draft">Ver rascunho</a>
    <a class="btn btn--ghost" href="/admin/page-builder/preview?status=published">Ver publicado</a>
  </div>
</header>
{ok_html}
<section class="panel">
  {render_login_page_preview(page, assets, blocks, preview_status)}
</section>
"""
    return admin_shell("Preview da pagina de login", content)


@app.post("/admin/page-builder/preview-submit")
@require_admin
def admin_page_builder_preview_submit():
    preview_status = request.form.get("preview_status", "draft")
    if preview_status not in ("draft", "published"):
        preview_status = "draft"
    return redirect(f"/admin/page-builder/preview?{urlencode({'status': preview_status, 'ok': 'preview'})}")


@app.post("/admin/page-builder/save")
@require_admin
def admin_page_builder_save():
    try:
        data, blocks = collect_builder_form()
        with get_conn() as conn:
            with conn.transaction():
                cur = conn.cursor()
                page = get_or_create_draft_login_page(cur)
                update_login_page_content(cur, page["id"], data)
                replace_benefit_blocks(cur, page["id"], blocks)
    except Exception as exc:
        return redirect(f"/admin/page-builder?{urlencode({'erro': str(exc)})}")
    return redirect("/admin/page-builder?ok=draft")


@app.post("/admin/page-builder/publish")
@require_admin
def admin_page_builder_publish():
    try:
        data, blocks = collect_builder_form()
        with get_conn() as conn:
            with conn.transaction():
                cur = conn.cursor()
                page = get_or_create_draft_login_page(cur)
                update_login_page_content(cur, page["id"], data)
                replace_benefit_blocks(cur, page["id"], blocks)
                publish_draft_login_page(cur)
    except Exception as exc:
        return redirect(f"/admin/page-builder?{urlencode({'erro': str(exc)})}")
    return redirect("/admin/page-builder?ok=publish")


@app.get("/admin/usuarios")
@require_admin
def admin_usuarios():
    filters = current_filters()
    page, per_page, offset = page_params()
    where = []
    params = []
    append_user_filters(where, params, filters, "u")
    sql = f"""
        SELECT
          u.id,
          u.nome,
          u.cpf,
          u.telefone,
          u.username_radius,
          u.ativo,
          u.criado_em,
          un.nome AS unidade,
          count(d.id) AS dispositivos
        FROM usuarios u
        JOIN unidades un ON un.id = u.unidade_id
        LEFT JOIN dispositivos d ON d.usuario_id = u.id
        {where_sql(where)}
        GROUP BY u.id, un.nome
        ORDER BY u.criado_em DESC
        LIMIT %s OFFSET %s
    """
    with get_conn() as conn:
        rows = conn.execute(sql, params + [per_page + 1, offset]).fetchall()

    has_next = len(rows) > per_page
    rows = rows[:per_page]
    table_rows = "".join(
        "<tr>"
        f"<td>{escape(row['id'])}</td>"
        f"<td>{escape(row['nome'])}</td>"
        f"<td>{escape(row['cpf'])}</td>"
        f"<td>{escape(row['telefone'])}</td>"
        f"<td>{escape(row['username_radius'])}</td>"
        f"<td>{escape(row['unidade'])}</td>"
        f"<td>{escape(row['dispositivos'])}</td>"
        f"<td>{status_badge(row['ativo'])}</td>"
        f"<td>{escape(row['criado_em'])}</td>"
        "</tr>"
        for row in rows
    ) or empty_row(9, "Nenhum usuario encontrado para os filtros atuais.")
    content = f"""
<header class="page-header">
  <div>
    <p class="eyebrow">Cadastro</p>
    <h1>Usuarios</h1>
  </div>
</header>

<section class="panel">
  <div class="panel-heading">
    <div>
      <h2>Busca de usuarios</h2>
      <p>Filtre por CPF, telefone, MAC vinculado ou IP visto em auditoria.</p>
    </div>
  </div>
  {filter_form("/admin/usuarios")}
</section>

<section class="panel">
  <div class="table-wrap">
    <table>
      <thead><tr><th>ID</th><th>Nome</th><th>CPF</th><th>Telefone</th><th>RADIUS</th><th>Unidade</th><th>Dispositivos</th><th>Ativo</th><th>Criado em</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </div>
  {pagination_links(page, has_next)}
</section>
"""
    return admin_shell("Usuarios", content)


@app.get("/admin/dispositivos")
@require_admin
def admin_dispositivos():
    filters = current_filters()
    page, per_page, offset = page_params()
    where = []
    params = []
    append_user_filters(where, params, filters, "u")
    sql = f"""
        SELECT
          d.id,
          d.mac,
          d.primeiro_acesso,
          d.ultimo_acesso,
          u.nome,
          u.cpf,
          u.telefone,
          u.username_radius
        FROM dispositivos d
        JOIN usuarios u ON u.id = d.usuario_id
        {where_sql(where)}
        ORDER BY d.ultimo_acesso DESC
        LIMIT %s OFFSET %s
    """
    with get_conn() as conn:
        rows = conn.execute(sql, params + [per_page + 1, offset]).fetchall()

    has_next = len(rows) > per_page
    rows = rows[:per_page]
    table_rows = "".join(
        "<tr>"
        f"<td>{escape(row['mac'])}</td>"
        f"<td>{escape(row['nome'])}</td>"
        f"<td>{escape(row['cpf'])}</td>"
        f"<td>{escape(row['telefone'])}</td>"
        f"<td>{escape(row['username_radius'])}</td>"
        f"<td>{escape(row['primeiro_acesso'])}</td>"
        f"<td>{escape(row['ultimo_acesso'])}</td>"
        "</tr>"
        for row in rows
    ) or empty_row(7, "Nenhum dispositivo encontrado para os filtros atuais.")
    content = f"""
<header class="page-header">
  <div>
    <p class="eyebrow">Inventario</p>
    <h1>Dispositivos</h1>
  </div>
</header>

<section class="panel">
  <div class="panel-heading">
    <div>
      <h2>Busca de dispositivos</h2>
      <p>Localize dispositivos por MAC, usuario, CPF, telefone ou IP interno.</p>
    </div>
  </div>
  {filter_form("/admin/dispositivos")}
</section>

<section class="panel">
  <div class="table-wrap">
    <table>
      <thead><tr><th>MAC</th><th>Usuario</th><th>CPF</th><th>Telefone</th><th>RADIUS</th><th>Primeiro acesso</th><th>Ultimo acesso</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </div>
  {pagination_links(page, has_next)}
</section>
"""
    return admin_shell("Dispositivos", content)


@app.get("/admin/sessoes")
@require_admin
def admin_sessoes():
    filters = current_filters()
    page, per_page, offset = page_params()
    where = []
    params = []
    if filters.get("cpf"):
        where.append("u.cpf = %s")
        params.append(filters["cpf"])
    if filters.get("telefone"):
        where.append("u.telefone = %s")
        params.append(filters["telefone"])
    if filters.get("mac"):
        where.append("r.callingstationid = %s")
        params.append(filters["mac"])
    if filters.get("ip"):
        where.append("r.framedipaddress = %s")
        params.append(filters["ip"])
    date_filter("r.acctstarttime", where, params)

    sql = f"""
        SELECT
          r.radacctid,
          r.username,
          r.callingstationid,
          r.framedipaddress,
          r.nasipaddress,
          r.acctstarttime,
          r.acctstoptime,
          r.acctsessiontime,
          r.acctinputoctets,
          r.acctoutputoctets,
          u.nome,
          u.cpf,
          u.telefone
        FROM radacct r
        LEFT JOIN usuarios u ON u.username_radius = r.username
        {where_sql(where)}
        ORDER BY COALESCE(r.acctstarttime, r.acctstoptime) DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    with get_conn() as conn:
        rows = conn.execute(sql, params + [per_page + 1, offset]).fetchall()

    has_next = len(rows) > per_page
    rows = rows[:per_page]
    table_rows = "".join(
        "<tr>"
        f"<td>{escape(row['username'])}</td>"
        f"<td>{escape(row['nome'])}</td>"
        f"<td>{escape(row['cpf'])}</td>"
        f"<td>{escape(row['telefone'])}</td>"
        f"<td>{escape(row['callingstationid'])}</td>"
        f"<td>{escape(row['framedipaddress'])}</td>"
        f"<td>{escape(row['nasipaddress'])}</td>"
        f"<td>{escape(row['acctstarttime'])}</td>"
        f"<td>{escape(row['acctstoptime'])}</td>"
        f"<td>{escape(row['acctsessiontime'])}</td>"
        "</tr>"
        for row in rows
    ) or empty_row(10, "Nenhuma sessao encontrada para os filtros atuais.")
    export_query = request.query_string.decode("utf-8")
    export_url = "/admin/export/sessoes.csv" + (f"?{export_query}" if export_query else "")
    content = f"""
<header class="page-header">
  <div>
    <p class="eyebrow">Accounting</p>
    <h1>Sessoes radacct</h1>
  </div>
  <a class="btn btn--primary" href="{escape(export_url)}">Exportar CSV</a>
</header>

<section class="panel">
  <div class="panel-heading">
    <div>
      <h2>Busca de sessoes</h2>
      <p>Use os filtros para investigar um acesso ou exportar o periodo selecionado.</p>
    </div>
  </div>
  {filter_form("/admin/sessoes", include_period=True)}
</section>

<section class="panel">
  <div class="table-wrap">
    <table>
      <thead><tr><th>RADIUS</th><th>Usuario</th><th>CPF</th><th>Telefone</th><th>MAC</th><th>IP interno</th><th>NAS IP</th><th>Inicio</th><th>Fim</th><th>Duracao</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </div>
  {pagination_links(page, has_next)}
</section>
"""
    return admin_shell("Sessoes", content)


@app.get("/admin/export/sessoes.csv")
@require_admin
def admin_export_sessoes():
    filters = current_filters()
    where = []
    params = []
    if filters.get("cpf"):
        where.append("u.cpf = %s")
        params.append(filters["cpf"])
    if filters.get("telefone"):
        where.append("u.telefone = %s")
        params.append(filters["telefone"])
    if filters.get("mac"):
        where.append("r.callingstationid = %s")
        params.append(filters["mac"])
    if filters.get("ip"):
        where.append("r.framedipaddress = %s")
        params.append(filters["ip"])
    date_filter("r.acctstarttime", where, params)

    sql = f"""
        SELECT
          u.nome,
          u.cpf,
          u.telefone,
          r.username AS username_radius,
          r.callingstationid AS mac,
          r.framedipaddress AS ip_interno,
          r.nasipaddress AS nas_ip,
          r.acctstarttime,
          r.acctstoptime,
          r.acctsessiontime,
          r.acctinputoctets,
          r.acctoutputoctets
        FROM radacct r
        LEFT JOIN usuarios u ON u.username_radius = r.username
        {where_sql(where)}
        ORDER BY r.acctstarttime DESC NULLS LAST
        LIMIT 10000
    """
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    output = StringIO()
    fieldnames = [
        "nome",
        "cpf",
        "telefone",
        "username_radius",
        "mac",
        "ip_interno",
        "nas_ip",
        "acctstarttime",
        "acctstoptime",
        "acctsessiontime",
        "acctinputoctets",
        "acctoutputoctets",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in fieldnames})

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=sessoes.csv"},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
