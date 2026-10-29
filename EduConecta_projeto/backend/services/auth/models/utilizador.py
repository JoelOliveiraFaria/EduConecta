"""Model: acesso aos dados da coleção `utilizadores`.

Cada função aqui faz só uma operação MongoDB e devolve dados crus (dicts,
ObjectId). Não valida input nem formata respostas HTTP — isso é
responsabilidade dos controllers que chamam estas funções.
"""

from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from werkzeug.security import generate_password_hash

from db import utilizadores


async def contar_colecoes():
    """Lista as coleções da base de dados — usado só para o health check /ready."""
    from db import database
    return await database.list_collection_names()


async def obter_por_email(email):
    """Devolve o documento do utilizador com este email, ou None se não existir."""
    return await utilizadores.find_one({"email": email})


async def obter_por_id(utilizador_id, projecao=None):
    """Devolve o utilizador pelo _id, com projeção opcional de campos."""
    return await utilizadores.find_one({"_id": ObjectId(utilizador_id)}, projecao)


async def existe_email(email, excluir_id=None):
    """Verifica rapidamente se já existe uma conta com este email (só projeta o _id).

    Com `excluir_id`, ignora essa própria conta na comparação — usado ao
    editar o email de um utilizador, para não rejeitar o próprio email dele.
    """
    filtro = {"email": email}
    if excluir_id is not None:
        filtro["_id"] = {"$ne": ObjectId(excluir_id)}
    return await utilizadores.find_one(filtro, {"_id": 1})


async def criar_encarregado(nome, email, password):
    """Cria uma conta com perfil 'encarregado' e estado 'pendente' (fluxo de /registo)."""
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
    """Cria uma conta já com perfil definido por um admin, estado 'provisionamento'
    e `deve_alterar_password=True` (fluxo de /admin/utilizadores + email de credenciais)."""
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
    """Ativa a conta depois do email de credenciais ter sido aceite pelo SMTP.

    O filtro inclui `estado: "provisionamento"` para só ativar a conta que
    acabou de ser criada — evita reativar uma conta que, entretanto, mudou
    de estado por outra via.
    """
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
    """Define uma nova password e desliga `deve_alterar_password` (fluxo /password/alterar)."""
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


async def atualizar_dados(utilizador_id, alteracoes):
    """Aplica um $set parcial (nome/email/perfil) e devolve a conta já atualizada (RF04)."""
    return await utilizadores.find_one_and_update(
        {"_id": ObjectId(utilizador_id)},
        {"$set": alteracoes},
        return_document=ReturnDocument.AFTER,
    )


async def desativar(utilizador_id):
    """Define estado 'inativo' (RF05). Devolve a conta já atualizada."""
    return await utilizadores.find_one_and_update(
        {"_id": ObjectId(utilizador_id)},
        {"$set": {"estado": "inativo", "desativado_em": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )


async def reativar(utilizador_id):
    """Reverte uma desativação, define estado 'ativo'. Devolve a conta já atualizada."""
    return await utilizadores.find_one_and_update(
        {"_id": ObjectId(utilizador_id)},
        {"$set": {"estado": "ativo"}, "$unset": {"desativado_em": ""}},
        return_document=ReturnDocument.AFTER,
    )


async def eliminar(utilizador_id, eliminado_por_id):
    """Soft delete (RF06): define estado 'eliminado' e guarda quem/quando.

    O documento nunca é removido da base de dados — só fica bloqueado em
    todo o resto do sistema, porque login/`/me`/tudo exige `estado == "ativo"`.
    """
    return await utilizadores.find_one_and_update(
        {"_id": ObjectId(utilizador_id)},
        {
            "$set": {
                "estado": "eliminado",
                "eliminado_em": datetime.now(timezone.utc),
                "eliminado_por": ObjectId(eliminado_por_id),
            },
        },
        return_document=ReturnDocument.AFTER,
    )
