"""Fixa qual serviço trata cada caminho, incluindo todas as colisões de prefixo
entre serviços. Se alguém mexer na tabela de rotas e uma rota passar para o
serviço errado, falha aqui."""

import pytest

from rotas import ROTAS, SERVICOS, corresponder

ID = "6ae24e41252e5bf6b58984ab"
OUTRO = "6ae24e41252e5bf6b58984ac"

# (método, caminho no gateway, serviço esperado, caminho que o serviço recebe, exige token)
CASOS = [
    # auth
    ("POST", "/api/login", "auth", "/login", False),
    ("GET", "/api/me", "auth", "/me", True),
    ("POST", "/api/password/alterar", "auth", "/password/alterar", True),
    ("POST", "/api/admin/utilizadores", "auth", "/admin/utilizadores", True),
    ("PATCH", f"/api/admin/utilizadores/{ID}", "auth", f"/admin/utilizadores/{ID}", True),
    ("POST", f"/api/admin/utilizadores/{ID}/desativar", "auth", f"/admin/utilizadores/{ID}/desativar", True),
    # escolar
    ("GET", "/api/alunos", "escolar", "/alunos", True),
    ("POST", "/api/alunos", "escolar", "/alunos", True),
    ("GET", f"/api/alunos/{ID}", "escolar", f"/alunos/{ID}", True),
    ("PUT", f"/api/alunos/{ID}/turma", "escolar", f"/alunos/{ID}/turma", True),
    ("GET", f"/api/alunos/{ID}/encarregados", "escolar", f"/alunos/{ID}/encarregados", True),
    ("PUT", f"/api/alunos/{ID}/encarregados/{OUTRO}", "escolar", f"/alunos/{ID}/encarregados/{OUTRO}", True),
    ("GET", "/api/encarregados", "escolar", "/encarregados", True),
    ("PUT", f"/api/encarregados/{ID}/utilizador", "escolar", f"/encarregados/{ID}/utilizador", True),
    ("GET", "/api/profissionais", "escolar", "/profissionais", True),
    ("GET", "/api/turmas", "escolar", "/turmas", True),
    ("GET", f"/api/turmas/{ID}", "escolar", f"/turmas/{ID}", True),
    ("GET", f"/api/turmas/{ID}/alunos", "escolar", f"/turmas/{ID}/alunos", True),
    ("PUT", f"/api/turmas/{ID}/profissionais/{OUTRO}", "escolar", f"/turmas/{ID}/profissionais/{OUTRO}", True),
    ("GET", "/api/me/alunos", "escolar", "/me/alunos", True),
    ("GET", "/api/me/turmas", "escolar", "/me/turmas", True),
    ("GET", f"/api/me/turmas/{ID}/alunos", "escolar", f"/me/turmas/{ID}/alunos", True),
    ("POST", "/api/me/chat/validar", "escolar", "/me/chat/validar", True),
    # diario (colide com /turmas/{id}/alunos e /me/alunos do escolar)
    ("POST", f"/api/turmas/{ID}/alunos/{OUTRO}/diario", "diario", f"/turmas/{ID}/alunos/{OUTRO}/diario", True),
    ("PATCH", f"/api/turmas/{ID}/alunos/{OUTRO}/diario/2026-03-05", "diario",
     f"/turmas/{ID}/alunos/{OUTRO}/diario/2026-03-05", True),
    ("GET", f"/api/me/alunos/{ID}/diario", "diario", f"/me/alunos/{ID}/diario", True),
    # assiduidade (colide com /turmas/{id}, /turmas/{id}/alunos e /alunos/{id} do escolar)
    ("GET", f"/api/turmas/{ID}/assiduidade", "assiduidade", f"/turmas/{ID}/assiduidade", True),
    ("PUT", f"/api/turmas/{ID}/alunos/{OUTRO}/assiduidade/2026-03-05", "assiduidade",
     f"/turmas/{ID}/alunos/{OUTRO}/assiduidade/2026-03-05", True),
    ("GET", f"/api/alunos/{ID}/assiduidade", "assiduidade", f"/alunos/{ID}/assiduidade", True),
    ("POST", f"/api/alunos/{ID}/faltas/2026-03-05/justificacao", "assiduidade",
     f"/alunos/{ID}/faltas/2026-03-05/justificacao", True),
    ("PUT", f"/api/alunos/{ID}/faltas/2026-03-05/justificacao/aprovar", "assiduidade",
     f"/alunos/{ID}/faltas/2026-03-05/justificacao/aprovar", True),
    ("GET", f"/api/alunos/{ID}/faltas/2026-03-05/justificacao/anexo", "assiduidade",
     f"/alunos/{ID}/faltas/2026-03-05/justificacao/anexo", True),
    # comunicados
    ("GET", f"/api/turmas/{ID}/comunicados", "comunicados", f"/turmas/{ID}/comunicados", True),
    ("PATCH", f"/api/turmas/{ID}/comunicados/{OUTRO}", "comunicados", f"/turmas/{ID}/comunicados/{OUTRO}", True),
    ("GET", "/api/conversas", "comunicados", "/conversas", True),
    ("POST", f"/api/conversas/{ID}/mensagens/video", "comunicados", f"/conversas/{ID}/mensagens/video", True),
    # notificacoes (colide com /me do auth)
    ("GET", "/api/me/notificacoes", "notificacoes", "/me/notificacoes", True),
    ("PATCH", f"/api/me/notificacoes/{ID}/lida", "notificacoes", f"/me/notificacoes/{ID}/lida", True),
    # documentação (pública)
    ("GET", "/api/openapi/auth.yaml", "auth", "/openapi.yaml", False),
    ("GET", "/api/openapi/assiduidade.yaml", "assiduidade", "/openapi.yaml", False),
]


@pytest.mark.parametrize("metodo,caminho,servico,caminho_servico,exige_token", CASOS)
async def test_rota_vai_para_o_servico_certo_sem_o_prefixo(
    client, servicos, cabecalhos_auth, metodo, caminho, servico, caminho_servico, exige_token
):
    resposta = await client.open(caminho, method=metodo, headers=cabecalhos_auth if exige_token else {})

    assert resposta.status_code == 200
    assert resposta.headers["X-Stub-Service"] == servico
    assert servicos.ultimo.url.host == servico
    assert servicos.ultimo.url.path == caminho_servico
    assert servicos.ultimo.method == metodo


@pytest.mark.parametrize("caminho", [
    f"/api/internal/turmas/{ID}/destinatarios",
    f"/api/internal/alunos/{ID}/destinatarios",
    f"/internal/turmas/{ID}/destinatarios",
    "/api/registo",
    "/api/ready/x",
    "/api/desconhecido",
    "/login",
    "/api",
    "/",
])
async def test_rotas_fora_da_tabela_nao_existem(client, servicos, cabecalhos_auth, caminho):
    resposta = await client.get(caminho, headers=cabecalhos_auth)

    assert resposta.status_code == 404
    assert (await resposta.get_json())["error"] == "not_found"
    assert servicos.pedidos == []


@pytest.mark.parametrize("caminho", [
    f"/api/alunos/../internal/turmas/{ID}/destinatarios",
    f"/api/alunos/./{ID}",
    f"/api/alunos/%2e%2e/internal/turmas/{ID}/destinatarios",
    f"/api/alunos/%2E%2E/internal/turmas/{ID}/destinatarios",
    f"/api/alunos/..%2finternal/turmas/{ID}/destinatarios",
    f"/api/alunos%2f..%2finternal",
    f"/api/alunos/..%5cinternal",
    f"/api//alunos/{ID}",
    f"/api/alunos//{ID}",
    f"/api/alunos/{ID}%00",
])
async def test_caminhos_que_tentam_contornar_a_tabela_sao_recusados(client, servicos, cabecalhos_auth, caminho):
    resposta = await client.get(caminho, headers=cabecalhos_auth)

    assert resposta.status_code == 404
    assert servicos.pedidos == []


def test_barra_final_e_ignorada():
    assert corresponder("/api/turmas/").id == "escolar-turmas"
    assert corresponder(f"/api/turmas/{ID}/").id == "escolar-turma"


def test_catch_all_casa_o_prefixo_sem_resto():
    assert corresponder("/api/alunos").id == "escolar-alunos"
    assert corresponder("/api/me/turmas").id == "escolar-me-turmas"
    assert corresponder("/api/conversas").id == "comunicados-conversas"


def test_literal_vence_parametro_e_parametro_vence_catch_all():
    assert corresponder(f"/api/alunos/{ID}/assiduidade").id == "assiduidade-aluno"
    assert corresponder(f"/api/alunos/{ID}/faltas/x/y").id == "assiduidade-faltas"
    assert corresponder(f"/api/alunos/{ID}/turma").id == "escolar-alunos"
    assert corresponder(f"/api/turmas/{ID}/alunos").id == "escolar-turma-alunos"
    assert corresponder(f"/api/turmas/{ID}/alunos/{OUTRO}/diario").id == "diario-turma"
    assert corresponder("/api/me").id == "auth-me"
    assert corresponder("/api/me/alunos").id == "escolar-me-alunos"
    assert corresponder(f"/api/me/alunos/{ID}/diario").id == "diario-me"


def test_tabela_nao_tem_ids_nem_caminhos_repetidos():
    assert len({rota.id for rota in ROTAS}) == len(ROTAS)
    assert len({rota.caminho for rota in ROTAS}) == len(ROTAS)
    assert all(rota.caminho.startswith("/api/") for rota in ROTAS)


def test_todos_os_servicos_tem_pelo_menos_uma_rota():
    assert {rota.servico for rota in ROTAS} == set(SERVICOS)


def test_so_o_login_e_a_documentacao_sao_publicos():
    publicas = {rota.id for rota in ROTAS if rota.publica}
    assert publicas == {"auth-login", *(f"openapi-{servico}" for servico in SERVICOS)}
