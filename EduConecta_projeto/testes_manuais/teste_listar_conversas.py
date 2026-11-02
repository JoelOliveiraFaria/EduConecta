import sys

from getpass import GetPassWarning

import teste_diario as apoio


COMUNICACAO = "http://127.0.0.1:8081/api"

CONVERSA = (
    "477a31abfcc00f8783a88869e33804e52"
    "b3db7425b5e4f9b475984fe223ee432"
)


def verificar_listagem(token, conta, campo_participante):
    cursor = None
    cursores_vistos = set()
    encontrada = False

    while True:
        caminho = "/conversas"

        if cursor is not None:
            caminho += f"?depois_de={cursor}"

        dados = apoio.verificar(
            apoio.pedido(
                COMUNICACAO,
                caminho,
                token=token,
            ),
            200,
            "Consulta da listagem de conversas",
        )

        conversas = dados.get("conversas")

        apoio.confirmar(
            isinstance(conversas, list),
            "Resposta contém uma lista de conversas",
        )

        apoio.confirmar(
            all(
                isinstance(item, dict)
                and item.get(campo_participante) == conta["id"]
                for item in conversas
            ),
            "Todas as conversas devolvidas incluem a conta autenticada",
        )

        if any(
            item.get("id") == CONVERSA
            for item in conversas
        ):
            encontrada = True

        if dados.get("tem_mais") is not True:
            break

        proximo = dados.get("proximo_cursor")

        apoio.confirmar(
            isinstance(proximo, str)
            and len(proximo) == 64
            and all(c in "0123456789abcdef" for c in proximo)
            and proximo not in cursores_vistos,
            "Cursor de paginação válido e não repetido",
        )

        cursores_vistos.add(proximo)
        cursor = proximo

    apoio.confirmar(
        encontrada,
        "Conversa do teste anterior encontrada na listagem",
    )

    apoio.verificar(
        apoio.pedido(
            COMUNICACAO,
            "/conversas?depois_de=invalido",
            token=token,
        ),
        400,
        "Cursor inválido recusado",
        "invalid_cursor",
    )


def principal():
    apoio.aprovados = 0

    print("TESTE DA LISTAGEM DE CONVERSAS")
    print("Este teste não cria conversas nem mensagens.\n")

    apoio.verificar(
        apoio.pedido(COMUNICACAO, "/conversas"),
        401,
        "Listagem sem sessão bloqueada",
        "authentication_required",
    )

    docente_token, docente = apoio.login(
        "docente",
        "docente",
    )

    verificar_listagem(
        docente_token,
        docente,
        "profissional_utilizador_id",
    )

    encarregado_token, encarregado = apoio.login(
        "encarregado",
        "encarregado",
    )

    verificar_listagem(
        encarregado_token,
        encarregado,
        "encarregado_utilizador_id",
    )

    print(
        f"\nTESTE CONCLUÍDO — "
        f"{apoio.aprovados} verificações aprovadas."
    )
    print("Nenhuma conversa ou mensagem foi criada ou alterada.")


if __name__ == "__main__":
    try:
        principal()
    except (KeyboardInterrupt, EOFError, GetPassWarning):
        print("\nTeste interrompido.")
        sys.exit(1)