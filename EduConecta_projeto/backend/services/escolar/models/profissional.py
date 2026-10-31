"""Model: acesso aos dados da coleção `profissionais` — sem validação nem formatação de resposta."""

from bson import ObjectId

from db import database

colecao = database["profissionais"]


def criar(utilizador_id, nome, perfil, cc, telemovel, morada="", data_admissao=None):
    """Insere um profissional novo, já ligado à conta de utilizador criada no auth."""
    profissional = {
        "utilizador_id": utilizador_id,
        "nome": nome,
        "perfil": perfil,
        "cc": cc,
        "telemovel": telemovel,
        "morada": morada,
        "data_admissao": data_admissao,
    }
    resultado = colecao.insert_one(profissional)
    return resultado.inserted_id, profissional


def listar():
    """Até 50 profissionais, por nome."""
    return (
        colecao
        .find(
            {},
            {
                "nome": 1, "perfil": 1, "utilizador_id": 1, "cc": 1, "telemovel": 1,
                "morada": 1, "data_admissao": 1,
            },
        )
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )


def obter(profissional_id):
    """Devolve um profissional pelo id, ou None se não existir."""
    return colecao.find_one(
        {"_id": ObjectId(profissional_id)},
        {
            "nome": 1, "perfil": 1, "utilizador_id": 1, "cc": 1, "telemovel": 1,
            "morada": 1, "data_admissao": 1,
        },
    )


def obter_por_utilizador(utilizador_id):
    """Encontra o registo de profissional ligado a esta conta de utilizador (sessão atual)."""
    return colecao.find_one(
        {"utilizador_id": utilizador_id},
        {"nome": 1, "perfil": 1, "utilizador_id": 1},
    )


def listar_por_ids(ids):
    """Profissionais cujo _id está na lista dada (usado para resolver os
    profissionais atribuídos a uma turma)."""
    return colecao.find(
        {"_id": {"$in": list(ids)}},
        {"nome": 1, "perfil": 1, "utilizador_id": 1},
    )


def obter_para_chat(utilizador_id):
    """Confirma que a conta é um profissional docente/educadora; usado na validação de chat
    (auxiliares ficam de fora de propósito — não participam em conversas de chat)."""
    return colecao.find_one(
        {"utilizador_id": utilizador_id, "perfil": {"$in": ["docente", "educadora"]}},
        {"perfil": 1},
    )
