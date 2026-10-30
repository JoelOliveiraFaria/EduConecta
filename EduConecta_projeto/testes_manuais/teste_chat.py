import sys
import uuid

from getpass import GetPassWarning

import teste_diario as apoio


COMUNICACAO = "http://127.0.0.1:8080/api"

pedido = apoio.pedido
verificar = apoio.verificar
confirmar = apoio.confirmar
falhar = apoio.falhar
login = apoio.login


def abrir_conversa(contexto, token, descricao):
    codigo, dados = pedido(
        COMUNICACAO,
        "/conversas",
        "POST",
        contexto,
        token,
    )

    if (
        codigo not in {200, 201}
        or not isinstance(dados, dict)
        or not isinstance(dados.get("conversa"), dict)
    ):
        print("HTTP recebido:", codigo)

        if isinstance(dados, dict):
            print("Erro:", dados.get("error"))
            print("Mensagem:", dados.get("message"))

        falhar(descricao)

    confirmar(True, descricao)

    conversa = dados["conversa"]

    confirmar(
        isinstance(conversa.get("id"), str)
        and len(conversa["id"]) == 64,
        "Conversa tem identificador válido",
    )

    confirmar(
        all(
            conversa.get(campo) == valor
            for campo, valor in contexto.items()
        ),
        "Conversa mantém o contexto autorizado",
    )

    return conversa["id"]


def localizar_mensagem(conversa_id, mensagem_id, token):
    caminho = f"/conversas/{conversa_id}/mensagens"
    cursor = None
    cursores_vistos = set()

    while True:
        rota = caminho

        if cursor is not None:
            rota += f"?antes_de={cursor}"

        dados = verificar(
            pedido(COMUNICACAO, rota, token=token),
            200,
            "Participante consulta mensagens",
        )

        mensagens = dados.get("mensagens")

        confirmar(
            isinstance(mensagens, list),
            "Resposta contém lista de mensagens",
        )

        for mensagem in mensagens:
            if (
                isinstance(mensagem, dict)
                and mensagem.get("id") == mensagem_id
            ):
                return mensagem

        if dados.get("tem_mais") is not True:
            falhar("Mensagem de teste não encontrada.")

        proximo_cursor = dados.get("proximo_cursor")

        if (
            not isinstance(proximo_cursor, str)
            or len(proximo_cursor) != 24
            or any(
                caractere not in "0123456789abcdef"
                for caractere in proximo_cursor
            )
            or proximo_cursor in cursores_vistos
        ):
            falhar("Cursor de paginação inválido ou repetido.")

        cursores_vistos.add(proximo_cursor)
        cursor = proximo_cursor


def principal():
    apoio.aprovados = 0

    print("TESTE DE INTEGRAÇÃO DO CHAT PRIVADO")
    print("Usar apenas as contas e o aluno de teste.")
    print("O teste pode criar uma conversa e criará duas mensagens.\n")

    ready = verificar(
        pedido(COMUNICACAO, "/ready"),
        200,
        "Base da Comunicação disponível",
    )

    confirmar(
        ready.get("services", {}).get("comunicados") == "ready",
        "Gateway confirma que o serviço está pronto, com a base ligada",
    )

    verificar(
        pedido(COMUNICACAO, "/conversas", "POST", {}),
        401,
        "Criação de conversa sem sessão bloqueada",
        "authentication_required",
    )

    docente_token, docente = login("docente", "docente")
    encarregado_token, encarregado = login(
        "encarregado",
        "encarregado",
    )

    contexto = {
        "aluno_id": apoio.ALUNO,
        "profissional_utilizador_id": docente["id"],
        "encarregado_utilizador_id": encarregado["id"],
    }

    validacao = verificar(
        pedido(
            apoio.SCHOOL,
            "/me/chat/validar",
            "POST",
            contexto,
            docente_token,
        ),
        200,
        "Escolar autoriza a relação pelo lado do docente",
    )

    confirmar(
        validacao.get("autorizado") is True,
        "Relação escolar confirmada para o docente",
    )

    validacao = verificar(
        pedido(
            apoio.SCHOOL,
            "/me/chat/validar",
            "POST",
            contexto,
            encarregado_token,
        ),
        200,
        "Escolar autoriza a relação pelo lado do encarregado",
    )

    confirmar(
        validacao.get("autorizado") is True,
        "Relação escolar confirmada para o encarregado",
    )

    contexto_invalido = {
        **contexto,
        "aluno_id": apoio.ALUNO_EXEMPLO,
    }

    verificar(
        pedido(
            COMUNICACAO,
            "/conversas",
            "POST",
            contexto_invalido,
            docente_token,
        ),
        404,
        "Conversa com aluno não acessível recusada",
    )

    contexto_alheio = {
        **contexto,
        "profissional_utilizador_id": "000000000000000000000002",
    }

    verificar(
        pedido(
            COMUNICACAO,
            "/conversas",
            "POST",
            contexto_alheio,
            docente_token,
        ),
        403,
        "Docente não pode abrir conversa em nome de outro profissional",
        "forbidden",
    )

    print("\nO próximo passo pode criar uma conversa de teste.")
    print("Depois serão guardadas duas mensagens de teste.")

    if input("Escreve TESTAR para continuar: ").strip() != "TESTAR":
        print("Teste cancelado antes das escritas previstas.")
        return

    conversa_id = abrir_conversa(
        contexto,
        docente_token,
        "Docente abre ou recupera a conversa",
    )

    print("ID da conversa:", conversa_id)

    conversa_encarregado = abrir_conversa(
        contexto,
        encarregado_token,
        "Encarregado abre ou recupera a mesma conversa",
    )

    confirmar(
        conversa_encarregado == conversa_id,
        "Os participantes usam a mesma conversa",
    )

    codigo, repetida = pedido(
        COMUNICACAO,
        "/conversas",
        "POST",
        contexto,
        docente_token,
    )

    confirmar(
        codigo == 200
        and isinstance(repetida, dict)
        and repetida.get("criada") is False
        and isinstance(repetida.get("conversa"), dict)
        and repetida["conversa"].get("id") == conversa_id,
        "Repetição devolve a conversa existente",
    )

    rota = f"/conversas/{conversa_id}/mensagens"

    verificar(
        pedido(COMUNICACAO, rota),
        401,
        "Consulta de mensagens sem sessão bloqueada",
        "authentication_required",
    )

    verificar(
        pedido(
            COMUNICACAO,
            rota,
            "POST",
            {"texto": "Não deve ser enviada."},
        ),
        401,
        "Envio de mensagem sem sessão bloqueado",
        "authentication_required",
    )

    verificar(
        pedido(
            COMUNICACAO,
            rota,
            "POST",
            {"texto": "   "},
            docente_token,
        ),
        400,
        "Mensagem vazia recusada",
        "invalid_text",
    )

    verificar(
        pedido(
            COMUNICACAO,
            rota,
            "POST",
            {
                "texto": "Não deve ser enviada.",
                "enviado_por": encarregado["id"],
            },
            docente_token,
        ),
        400,
        "Remetente enviado pelo cliente recusado",
        "invalid_fields",
    )

    referencia = uuid.uuid4().hex[:12]
    texto_docente = f"[TESTE {referencia}] Mensagem do docente."
    texto_encarregado = (
        f"[TESTE {referencia}] Resposta do encarregado."
    )

    enviada_docente = verificar(
        pedido(
            COMUNICACAO,
            rota,
            "POST",
            {"texto": texto_docente},
            docente_token,
        ),
        201,
        "Docente envia mensagem",
    )

    confirmar(
        isinstance(enviada_docente.get("id"), str)
        and bool(enviada_docente["id"]),
        "Mensagem do docente recebe identificador",
    )

    confirmar(
        enviada_docente.get("texto") == texto_docente
        and enviada_docente.get("conversa_id") == conversa_id
        and enviada_docente.get("enviada_por_mim") is True,
        "Resposta do envio identifica a mensagem do docente",
    )

    recebida = localizar_mensagem(
        conversa_id,
        enviada_docente["id"],
        encarregado_token,
    )

    confirmar(
        recebida.get("texto") == texto_docente
        and recebida.get("enviada_por_mim") is False,
        "Encarregado consulta a mensagem recebida do docente",
    )

    enviada_encarregado = verificar(
        pedido(
            COMUNICACAO,
            rota,
            "POST",
            {"texto": texto_encarregado},
            encarregado_token,
        ),
        201,
        "Encarregado responde à conversa",
    )

    confirmar(
        isinstance(enviada_encarregado.get("id"), str)
        and bool(enviada_encarregado["id"]),
        "Mensagem do encarregado recebe identificador",
    )

    confirmar(
        enviada_encarregado.get("texto") == texto_encarregado
        and enviada_encarregado.get("enviada_por_mim") is True,
        "Resposta do envio identifica a mensagem do encarregado",
    )

    resposta = localizar_mensagem(
        conversa_id,
        enviada_encarregado["id"],
        docente_token,
    )

    confirmar(
        resposta.get("texto") == texto_encarregado
        and resposta.get("enviada_por_mim") is False,
        "Docente consulta a resposta recebida do encarregado",
    )

    confirmar(
        all(
            "enviado_por" not in item
            for item in (
                enviada_docente,
                recebida,
                enviada_encarregado,
                resposta,
            )
        ),
        "Identificador interno do remetente não exposto nas mensagens",
    )

    print(
        f"\nTESTE CONCLUÍDO — "
        f"{apoio.aprovados} verificações aprovadas."
    )
    print("Conversa:", conversa_id)
    print("Mensagem docente:", enviada_docente["id"])
    print("Mensagem encarregado:", enviada_encarregado["id"])
    print("As duas mensagens de teste permanecem guardadas.")
    print("O canal e o Diário não foram alterados.")


if __name__ == "__main__":
    try:
        principal()
    except (KeyboardInterrupt, EOFError, GetPassWarning):
        print("\nTeste interrompido.")
        print("As escritas já realizadas podem permanecer na base.")
        sys.exit(1)