from datetime import datetime, timezone

from bson import ObjectId
from werkzeug.security import generate_password_hash

from db import utilizadores


async def contar_colecoes():
    from db import database
    return await database.list_collection_names()


async def obter_por_email(email):
    return await utilizadores.find_one({"email": email})


async def obter_por_id(utilizador_id, projecao=None):
    return await utilizadores.find_one({"_id": ObjectId(utilizador_id)}, projecao)


async def existe_email(email):
    return await utilizadores.find_one({"email": email}, {"_id": 1})


async def criar_encarregado(nome, email, password):
    documento = {
        "nome": nome,
        "email": email,
        "password_hash": generate_password_hash(password, method="scrypt"),
        "perfil": "encarregado",
        "estado": "pendente",
        "criado_em": datetime.now(timezone.utc),
    }
    resultado = await utilizadores.insert_one(documento)
    return resultado.inserted_id, documento


async def criar_com_password_temporaria(nome, email, perfil, password_temporaria, criado_por_id):
    documento = {
        "nome": nome,
        "email": email,
        "perfil": perfil,
        "estado": "provisionamento",
        "password_hash": generate_password_hash(password_temporaria, method="scrypt"),
        "deve_alterar_password": True,
        "criado_em": datetime.now(timezone.utc),
        "criado_por": ObjectId(criado_por_id),
        "email_credenciais_estado": "pendente",
    }
    resultado = await utilizadores.insert_one(documento)
    return resultado.inserted_id, documento


async def marcar_email_credenciais_enviado(conta_id):
    return await utilizadores.update_one(
        {"_id": conta_id, "estado": "provisionamento"},
        {
            "$set": {
                "estado": "ativo",
                "email_credenciais_estado": "aceite_pelo_smtp",
                "email_credenciais_enviado_em": datetime.now(timezone.utc),
            },
        },
    )


async def atualizar_password(utilizador_id, password_nova):
    await utilizadores.update_one(
        {"_id": utilizador_id},
        {
            "$set": {
                "password_hash": generate_password_hash(password_nova, method="scrypt"),
                "deve_alterar_password": False,
                "password_alterada_em": datetime.now(timezone.utc),
            },
            "$unset": {"password_temporaria_expira_em": ""},
        },
    )
