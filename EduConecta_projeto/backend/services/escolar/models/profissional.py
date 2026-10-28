from bson import ObjectId

from db import database

colecao = database["profissionais"]


def existe_por_utilizador(utilizador_id):
    return colecao.find_one({"utilizador_id": utilizador_id}, {"_id": 1})


def criar(utilizador_id, nome, perfil):
    profissional = {"utilizador_id": utilizador_id, "nome": nome, "perfil": perfil}
    resultado = colecao.insert_one(profissional)
    return resultado.inserted_id, profissional


def listar():
    return (
        colecao
        .find({}, {"nome": 1, "perfil": 1, "utilizador_id": 1})
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )


def obter(profissional_id):
    return colecao.find_one(
        {"_id": ObjectId(profissional_id)},
        {"nome": 1, "perfil": 1, "utilizador_id": 1},
    )


def obter_por_utilizador(utilizador_id):
    return colecao.find_one(
        {"utilizador_id": utilizador_id},
        {"nome": 1, "perfil": 1, "utilizador_id": 1},
    )


def obter_para_chat(utilizador_id):
    return colecao.find_one(
        {"utilizador_id": utilizador_id, "perfil": {"$in": ["docente", "educadora"]}},
        {"perfil": 1},
    )
