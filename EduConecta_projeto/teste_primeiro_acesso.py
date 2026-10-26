import secrets
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
from app import app, database

email = f"teste-{secrets.token_hex(8)}@example.com"
temporaria = secrets.token_urlsafe(24)
nova = secrets.token_urlsafe(24)
utilizador_id = None


def verificar(resposta, codigo, descricao, erro=None):
    dados = resposta.get_json(silent=True) or {}

    if resposta.status_code != codigo:
        raise RuntimeError(
            f"{descricao}: esperado {codigo}, "
            f"recebido {resposta.status_code}; "
            f"erro={dados.get('error')}"
        )

    if erro and dados.get("error") != erro:
        raise RuntimeError(
            f"{descricao}: erro inesperado {dados.get('error')}"
        )

    print(f"OK - {descricao}")
    return dados


try:
    resultado = database["utilizadores"].insert_one({
        "nome": "Teste Primeiro Acesso",
        "email": email,
        "password_hash": generate_password_hash(
            temporaria,
            method="scrypt",
        ),
        "perfil": "encarregado",
        "estado": "ativo",
        "deve_alterar_password": True,
        "criado_em": datetime.now(timezone.utc),
    })
    utilizador_id = resultado.inserted_id

    with app.test_client() as cliente:
        resposta = cliente.post("/login", json={
            "email": email,
            "password": temporaria,
        })
        dados = verificar(resposta, 200, "Login temporário")
        headers = {
            "Authorization": "Bearer " + dados["access_token"]
        }

        resposta = cliente.get("/me", headers=headers)
        verificar(
            resposta,
            403,
            "Acesso bloqueado antes da troca",
            "password_change_required",
        )

        resposta = cliente.post(
            "/password/alterar",
            headers=headers,
            json={
                "password_atual": temporaria,
                "password_nova": nova,
            },
        )
        verificar(resposta, 200, "Palavra-passe alterada")

        resposta = cliente.post("/login", json={
            "email": email,
            "password": temporaria,
        })
        verificar(
            resposta,
            401,
            "Palavra-passe temporária rejeitada",
            "invalid_credentials",
        )

        resposta = cliente.post("/login", json={
            "email": email,
            "password": nova,
        })
        dados = verificar(resposta, 200, "Novo login")
        headers = {
            "Authorization": "Bearer " + dados["access_token"]
        }

        resposta = cliente.get("/me", headers=headers)
        verificar(resposta, 200, "Acesso permitido após a troca")

finally:
    if utilizador_id is not None:
        resultado = database["utilizadores"].delete_one({
            "_id": utilizador_id,
            "email": email,
        })
        print("Contas de teste removidas:", resultado.deleted_count)