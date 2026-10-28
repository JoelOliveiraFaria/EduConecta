import sys
import uuid

from getpass import GetPassWarning

import teste_diario as apoio


COMUNICADOS = "http://127.0.0.1:5004"

TURMA = apoio.TURMA
ALUNO = apoio.ALUNO
TURMA_EXEMPLO = apoio.TURMA_EXEMPLO

ROTA = f"/turmas/{TURMA}/comunicados"
ROTA_OUTRA_TURMA = f"/turmas/{TURMA_EXEMPLO}/comunicados"

pedido = apoio.pedido
verificar = apoio.verificar
confirmar = apoio.confirmar
falhar = apoio.falhar
login = apoio.login


def consultar_e_localizar(token, comunicado_id, descricao):
    for pagina in range(1, 1001):
        dados = verificar(
            pedido(
                COMUNICADOS,
                f"{ROTA}?pagina={pagina}",
                token=token,
            ),
            200,
            f"{descricao} — página {pagina}",
        )

        comunicados = dados.get("comunicados")

        confirmar(
            isinstance(comunicados, list),
            "Resposta contém uma lista de comunicados",
        )

        for comunicado in comunicados:
            if (
                isinstance(comunicado, dict)
                and comunicado.get("id") == comunicado_id
            ):
                return comunicado

        if dados.get("tem_mais") is not True:
            break

    falhar("O comunicado criado não foi encontrado na consulta.")


def principal():
    apoio.aprovados = 0

    print("TESTE DE INTEGRAÇÃO DOS COMUNICADOS")
    print("Usar apenas as contas e a turma de teste.")
    print("O teste criará um comunicado e mantê-lo-á na base.\n")

    verificar(
        pedido(COMUNICADOS, "/health"),
        200,
        "Aplicação Comunicados disponível",
    )

    ready = verificar(
        pedido(COMUNICADOS, "/ready"),
        200,
        "Base dos Comunicados disponível",
    )

    confirmar(
        ready.get("database") == "connected",
        "Serviço confirma ligação à base",
    )

    verificar(
        pedido(COMUNICADOS, ROTA),
        401,
        "Consulta sem sessão bloqueada",
        "authentication_required",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA,
            "POST",
            {"titulo": "Teste", "texto": "Não deve ser criado."},
        ),
        401,
        "Publicação sem sessão bloqueada",
        "authentication_required",
    )

    docente_token, _ = login("docente", "docente")
    encarregado_token, _ = login("encarregado", "encarregado")

    educandos = verificar(
        pedido(
            apoio.SCHOOL,
            "/me/alunos",
            token=encarregado_token,
        ),
        200,
        "Consulta dos educandos associados",
    )

    confirmar(
        any(
            isinstance(item, dict)
            and item.get("id") == ALUNO
            and item.get("turma_id") == TURMA
            for item in educandos.get("alunos", [])
        ),
        "Educando de teste associado à turma e ao encarregado",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA,
            token=docente_token,
        ),
        200,
        "Docente pode consultar os comunicados da turma",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA,
            token=encarregado_token,
        ),
        200,
        "Encarregado pode consultar os comunicados da turma",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA,
            "POST",
            {"titulo": "Teste recusado", "texto": "Não deve ser criado."},
            encarregado_token,
        ),
        403,
        "Encarregado não pode publicar",
        "forbidden",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA_OUTRA_TURMA,
            token=encarregado_token,
        ),
        404,
        "Encarregado não pode consultar turma não associada",
        "class_not_accessible",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA_OUTRA_TURMA,
            token=docente_token,
        ),
        404,
        "Docente não pode consultar turma não acessível",
        "resource_not_accessible",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA_OUTRA_TURMA,
            "POST",
            {"titulo": "Teste recusado", "texto": "Não deve ser criado."},
            docente_token,
        ),
        404,
        "Docente não pode publicar em turma não acessível",
        "resource_not_accessible",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA,
            "POST",
            {"titulo": "   ", "texto": "Texto de teste."},
            docente_token,
        ),
        400,
        "Título vazio recusado",
        "invalid_title",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA,
            "POST",
            {"titulo": "Título de teste", "texto": "   "},
            docente_token,
        ),
        400,
        "Texto vazio recusado",
        "invalid_text",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA,
            "POST",
            {
                "titulo": "Título de teste",
                "texto": "Texto de teste.",
                "criado_por": "nao_permitido",
            },
            docente_token,
        ),
        400,
        "Campo adicional criado_por recusado",
        "invalid_fields",
    )

    verificar(
        pedido(
            COMUNICADOS,
            ROTA + "?pagina=0",
            token=docente_token,
        ),
        400,
        "Página inválida recusada",
        "invalid_page",
    )

    referencia = uuid.uuid4().hex[:12]

    payload = {
        "titulo": f"[TESTE INTEGRAÇÃO] Comunicado {referencia}",
        "texto": (
            "Comunicado criado pelo teste automático da EduConecta. "
            "Serve apenas para validar publicação e consulta. "
            f"Referência: {referencia}."
        ),
    }

    print("\nAs verificações anteriores terminaram sem criar comunicados.")
    print("O próximo pedido criará um comunicado na turma:", TURMA)

    autorizacao = input(
        "Escreve CRIAR para autorizar esta publicação de teste: "
    ).strip()

    if autorizacao != "CRIAR":
        print("Publicação cancelada. Nenhum comunicado de teste foi criado.")
        return

    criado = verificar(
        pedido(
            COMUNICADOS,
            ROTA,
            "POST",
            payload,
            docente_token,
        ),
        201,
        "Docente publica um comunicado",
    )

    comunicado_id = criado.get("id")

    confirmar(
        isinstance(comunicado_id, str) and bool(comunicado_id),
        "Comunicado recebe identificador",
    )

    print("ID do comunicado de teste:", comunicado_id)

    confirmar(
        criado.get("turma_id") == TURMA
        and criado.get("titulo") == payload["titulo"]
        and criado.get("texto") == payload["texto"],
        "Resposta da publicação mantém a turma e o conteúdo",
    )

    profissional = consultar_e_localizar(
        docente_token,
        comunicado_id,
        "Docente consulta o comunicado guardado",
    )

    familiar = consultar_e_localizar(
        encarregado_token,
        comunicado_id,
        "Encarregado consulta o comunicado guardado",
    )

    for descricao, documento in (
        ("docente", profissional),
        ("encarregado", familiar),
    ):
        confirmar(
            documento.get("turma_id") == TURMA
            and documento.get("titulo") == payload["titulo"]
            and documento.get("texto") == payload["texto"]
            and documento.get("criado_em") == criado.get("criado_em"),
            f"Conteúdo e data mantidos na consulta do {descricao}",
        )

    confirmar(
        "criado_por" not in familiar,
        "Identificador da conta autora não exposto ao encarregado",
    )

    print(
        f"\nTESTE CONCLUÍDO — "
        f"{apoio.aprovados} verificações aprovadas."
    )
    print("Foi criado um comunicado de teste.")
    print("ID:", comunicado_id)
    print("Nenhum registo do Diário foi alterado.")


if __name__ == "__main__":
    try:
        principal()
    except (KeyboardInterrupt, EOFError, GetPassWarning):
        print("\nTeste interrompido.")
        print("Se a publicação já ocorreu, o comunicado permanece na base.")
        sys.exit(1)