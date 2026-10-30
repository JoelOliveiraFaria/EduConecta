"""Utilitário: validação dos tokens JWT emitidos pelo serviço auth.

O gateway só verifica o que se pode saber sem consultar ninguém: assinatura,
validade, emissor e audiência. Se a conta ainda existe, está ativa ou tem de
mudar a palavra-passe continua a ser decidido pelo `/me` do auth, que cada
serviço chama — por isso um token válido aqui não garante acesso.
"""

import jwt

EMISSOR = "educonecta-auth"
AUDIENCIA = "educonecta-api"
_OBRIGATORIOS = ["sub", "iss", "aud", "iat", "exp", "jti"]
_MAX_CABECALHO = 8192


def autenticar(autorizacao, segredo):
    """Valida o cabeçalho Authorization: Bearer <token>.

    Devolve (claims, None) se válido, ou (None, (codigo, mensagem)) com o
    mesmo código e texto de erro que o auth usa.
    """
    partes = autorizacao.split()

    if len(autorizacao) > _MAX_CABECALHO or len(partes) != 2 or partes[0].lower() != "bearer":
        return None, ("authentication_required", "Envia um token no cabeçalho Authorization: Bearer.")

    try:
        claims = jwt.decode(
            partes[1],
            segredo,
            algorithms=["HS256"],
            issuer=EMISSOR,
            audience=AUDIENCIA,
            options={"require": _OBRIGATORIOS},
        )
    except jwt.ExpiredSignatureError:
        return None, ("token_expired", "A sessão expirou. Inicia sessão novamente.")
    except jwt.InvalidTokenError:
        return None, ("invalid_token", "O token é inválido.")

    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        return None, ("invalid_token", "O token é inválido.")

    return claims, None
