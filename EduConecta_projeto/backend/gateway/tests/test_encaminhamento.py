"""Como o gateway reencaminha o pedido e devolve a resposta do serviço."""

import httpx

from conftest import fazer_token


async def test_query_string_segue_intacta(client, servicos, cabecalhos_auth):
    await client.get("/api/me/turmas?pagina=2&nome=Jo%C3%A3o", headers=cabecalhos_auth)

    assert servicos.ultimo.url.query == b"pagina=2&nome=Jo%C3%A3o"


async def test_corpo_e_tipo_de_conteudo_seguem_intactos(client, servicos, cabecalhos_auth):
    corpo = b'{"estado": "falta", "versao": 0}'

    await client.put(
        "/api/turmas/6ae24e41252e5bf6b58984ab/alunos/6ae24e41252e5bf6b58984ac/assiduidade/2026-03-05",
        data=corpo, headers={**cabecalhos_auth, "Content-Type": "application/json"},
    )

    assert servicos.ultimo.content == corpo
    assert servicos.cabecalho_recebido("Content-Type") == "application/json"


async def test_resposta_do_servico_chega_tal_como_veio(client, servicos, cabecalhos_auth):
    servicos.respostas["escolar"] = (
        403,
        {"content-type": "application/json", "cache-control": "no-store", "x-extra": "1"},
        '{"error":"school_profile_not_linked","message":"Sem registo escolar."}'.encode(),
    )

    resposta = await client.get("/api/me/alunos", headers=cabecalhos_auth)

    assert resposta.status_code == 403
    assert resposta.headers["Cache-Control"] == "no-store"
    assert resposta.headers["X-Extra"] == "1"
    assert (await resposta.get_json())["error"] == "school_profile_not_linked"


async def test_erros_do_proprio_servico_nao_sao_reescritos(client, servicos, cabecalhos_auth):
    """Só as falhas do gateway ganham corpo JSON próprio; um 404 ou 503 do serviço passa como está."""
    servicos.respostas["escolar"] = (404, {"content-type": "application/json"}, b'{"error":"student_not_found"}')
    resposta = await client.get("/api/alunos/6ae24e41252e5bf6b58984ab", headers=cabecalhos_auth)
    assert resposta.status_code == 404
    assert (await resposta.get_json())["error"] == "student_not_found"

    servicos.respostas["escolar"] = (503, {"content-type": "application/json"}, b'{"error":"database_unavailable"}')
    resposta = await client.get("/api/alunos/6ae24e41252e5bf6b58984ab", headers=cabecalhos_auth)
    assert resposta.status_code == 503
    assert (await resposta.get_json())["error"] == "database_unavailable"


async def test_resposta_binaria_passa_sem_alteracao(client, servicos, cabecalhos_auth):
    anexo = bytes(range(256)) * 40
    servicos.respostas["assiduidade"] = (200, {"content-type": "application/pdf"}, anexo)

    resposta = await client.get(
        "/api/alunos/6ae24e41252e5bf6b58984ab/faltas/2026-03-05/justificacao/anexo", headers=cabecalhos_auth
    )

    assert await resposta.get_data() == anexo
    assert resposta.headers["Content-Type"] == "application/pdf"


async def test_cabecalhos_que_so_valem_entre_servicos_nao_entram_pela_porta_do_gateway(
    client, servicos, cabecalhos_auth
):
    await client.get("/api/me/notificacoes", headers={
        **cabecalhos_auth,
        "X-Internal-Key": "tentativa-de-falsificar",
        "X-Forwarded-For": "6.6.6.6",
        "X-Forwarded-Host": "falso.example",
    })

    assert servicos.cabecalho_recebido("X-Internal-Key") is None
    assert "6.6.6.6" not in servicos.cabecalho_recebido("X-Forwarded-For")
    assert servicos.cabecalho_recebido("X-Forwarded-Host") != "falso.example"


async def test_gateway_identifica_o_pedido_para_os_servicos(client, servicos, cabecalhos_auth):
    resposta = await client.get("/api/me/notificacoes", headers={**cabecalhos_auth, "X-Request-Id": "pedido-123"})

    assert servicos.cabecalho_recebido("X-Request-Id") == "pedido-123"
    assert resposta.headers["X-Request-Id"] == "pedido-123"
    assert servicos.cabecalho_recebido("X-Forwarded-For") is not None


async def test_servico_em_baixo_devolve_erro_json_no_formato_dos_servicos(client, servicos, cabecalhos_auth):
    servicos.erros["notificacoes"] = httpx.ConnectError("serviço em baixo (simulado)")

    resposta = await client.get("/api/me/notificacoes", headers=cabecalhos_auth)

    assert resposta.status_code == 502
    corpo = await resposta.get_json()
    assert corpo["error"] == "dependency_unavailable"
    assert resposta.mimetype == "application/json"


async def test_servico_lento_devolve_504(client, servicos, cabecalhos_auth):
    servicos.erros["notificacoes"] = httpx.ReadTimeout("demorou demasiado (simulado)")

    resposta = await client.get("/api/me/notificacoes", headers=cabecalhos_auth)

    assert resposta.status_code == 504
    assert (await resposta.get_json())["error"] == "dependency_timeout"


async def test_servico_marcado_como_indisponivel_nao_recebe_pedidos(app, client, servicos, cabecalhos_auth):
    monitor = app.extensions["monitor_saude"]
    for _ in range(3):
        monitor._falhas["notificacoes"] += 1

    resposta = await client.get("/api/me/notificacoes", headers=cabecalhos_auth)

    assert resposta.status_code == 503
    assert (await resposta.get_json())["error"] == "dependency_unavailable"
    assert servicos.pedidos == []

    # Os outros serviços não são afetados.
    assert (await client.get("/api/me", headers=cabecalhos_auth)).status_code == 200


async def test_corpo_acima_do_limite_da_rota_e_recusado_sem_chegar_ao_servico(client, servicos):
    resposta = await client.post("/api/login", data=b"x" * (16 * 1024 + 1))

    assert resposta.status_code == 413
    assert (await resposta.get_json())["error"] == "payload_too_large"
    assert servicos.pedidos == []


async def test_corpo_no_limite_da_rota_passa(client, servicos):
    resposta = await client.post("/api/login", data=b"x" * (16 * 1024))

    assert resposta.status_code == 200
    assert len(servicos.ultimo.content) == 16 * 1024


async def test_cada_rota_tem_o_seu_limite(client, servicos, cabecalhos_auth):
    """Os comunicados aceitam vídeos até 25 MB; a assiduidade só 6 MB; o diário só 16 KB."""
    cinco_mb = b"x" * (5 * 1024 * 1024)

    comunicado = await client.post("/api/conversas/6ae24e41252e5bf6b58984ab/mensagens/video",
                                   data=cinco_mb, headers=cabecalhos_auth)
    assert comunicado.status_code == 200

    anexo = await client.post("/api/alunos/6ae24e41252e5bf6b58984ab/faltas/2026-03-05/justificacao",
                              data=cinco_mb, headers=cabecalhos_auth)
    assert anexo.status_code == 200

    diario = await client.post(
        "/api/turmas/6ae24e41252e5bf6b58984ab/alunos/6ae24e41252e5bf6b58984ac/diario",
        data=b"x" * (17 * 1024), headers=cabecalhos_auth,
    )
    assert diario.status_code == 413


async def test_o_limite_da_assiduidade_e_6_mb(client, servicos, cabecalhos_auth):
    resposta = await client.post("/api/alunos/6ae24e41252e5bf6b58984ab/faltas/2026-03-05/justificacao",
                                 data=b"x" * (6 * 1024 * 1024 + 1), headers=cabecalhos_auth)

    assert resposta.status_code == 413
    assert servicos.pedidos == []


async def test_uma_rota_sem_limite_proprio_usa_o_padrao_de_1_mb(client, servicos, cabecalhos_auth):
    resposta = await client.post("/api/alunos", data=b"x" * (1024 * 1024 + 1), headers=cabecalhos_auth)

    assert resposta.status_code == 413
    assert servicos.pedidos == []


async def test_um_token_valido_nao_dispensa_a_rota(client, servicos, cabecalhos_auth):
    """Autenticado não quer dizer autorizado a chegar a qualquer sítio: só o que está na tabela."""
    resposta = await client.get("/api/internal/turmas/6ae24e41252e5bf6b58984ab/destinatarios",
                                headers={"Authorization": f"Bearer {fazer_token()}"})

    assert resposta.status_code == 404
    assert servicos.pedidos == []
