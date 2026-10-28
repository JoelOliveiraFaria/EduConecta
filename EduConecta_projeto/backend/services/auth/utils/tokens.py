"""Utilitário: emissão e validação de tokens JWT de sessão.

Usado pelos controllers para gerar o token no login e para descodificá-lo
em todas as rotas protegidas (/me, /password/alterar, rotas de admin).
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from bson import ObjectId
from quart import jsonify

jwt_secret = os.environ["JWT_SECRET_KEY"]

# Falha cedo no arranque do serviço em vez de emitir tokens fracos.
if len(jwt_secret) < 32:
    raise RuntimeError("A chave JWT deve ter pelo menos 32 caracteres.")


def gerar_token(utilizador_id):
    """Cria um JWT HS256 válido por 15 minutos, com jti único por token."""
    agora = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(utilizador_id),
            "iss": "educonecta-auth",
            "aud": "educonecta-api",
            "iat": agora,
            "exp": agora + timedelta(minutes=15),
            "jti": secrets.token_hex(16),
        },
        jwt_secret,
        algorithm="HS256",
    )


def descodificar_token(autorizacao):
    """Valida o cabeçalho Authorization: Bearer <token>.

    Devolve (utilizador_id, None) se válido, ou (None, resposta_erro) — uma
    tupla (jsonify(...), status, headers) pronta a devolver diretamente pelo
    controller — para token em falta, expirado ou inválido.
    """
    partes = autorizacao.split()

    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None, (
            jsonify({
                "error": "authentication_required",
                "message": "Envia um token no cabeçalho Authorization: Bearer.",
            }),
            401,
            {"WWW-Authenticate": "Bearer"},
        )

    try:
        conteudo = jwt.decode(
            partes[1],
            jwt_secret,
            algorithms=["HS256"],
            issuer="educonecta-auth",
            audience="educonecta-api",
            options={
                "require": ["sub", "iss", "aud", "iat", "exp", "jti"],
            },
        )

    except jwt.ExpiredSignatureError:
        return None, (
            jsonify({
                "error": "token_expired",
                "message": "A sessão expirou. Inicia sessão novamente.",
            }),
            401,
            {"WWW-Authenticate": "Bearer"},
        )

    except jwt.InvalidTokenError:
        return None, (
            jsonify({
                "error": "invalid_token",
                "message": "O token é inválido.",
            }),
            401,
            {"WWW-Authenticate": "Bearer"},
        )

    utilizador_id = conteudo.get("sub")

    if not isinstance(utilizador_id, str) or not ObjectId.is_valid(utilizador_id):
        return None, (
            jsonify({
                "error": "invalid_token",
                "message": "O token é inválido.",
            }),
            401,
            {"WWW-Authenticate": "Bearer"},
        )

    return utilizador_id, None
