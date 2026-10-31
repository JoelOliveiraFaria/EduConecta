import json
import sys
import warnings

from getpass import getpass, GetPassWarning
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


warnings.simplefilter("error", GetPassWarning)

AUTH = "http://127.0.0.1:8081/api"
SCHOOL = "http://127.0.0.1:8081/api"
DIARIO = "http://127.0.0.1:8081/api"

TURMA = "6ae0caf50852a73f69bac39e"
ALUNO = "6ae0caf54d0d7ddbc83796c7"
DATA = "2026-10-28"

TURMA_EXEMPLO = "000000000000000000000001"
ALUNO_EXEMPLO = "000000000000000000000001"

ROTA = f"/turmas/{TURMA}/alunos/{ALUNO}/diario"
ROTA_ENCARREGADO = f"/me/alunos/{ALUNO}/diario"

CAMPOS = (
    "alimentacao",
    "sono",
    "higiene",
    "atividades",
    "observacoes",
)

aprovados = 0


def falhar(mensagem):
    print("\nFALHOU - " + mensagem)
    sys.exit(1)


def confirmar(condicao, descricao):
    global aprovados

    if not condicao:
        falhar(descricao)

    aprovados += 1
    print("OK - " + descricao)


def pedido(base, caminho, metodo="GET", dados=None, token=None):
    headers = {"Accept": "application/json"}
    corpo = None

    if dados is not None:
        headers["Content-Type"] = "application/json"
        corpo = json.dumps(dados).encode("utf-8")

    if token:
        headers["Authorization"] = "Bearer " + token

    requisicao = Request(
        base + caminho,
        data=corpo,
        headers=headers,
        method=metodo,
    )

    try:
        with urlopen(requisicao, timeout=20) as resposta:
            return resposta.status, json.load(resposta)

    except HTTPError as exc:
        codigo = exc.code
        corpo = exc.read()
        exc.close()

        try:
            return codigo, json.loads(corpo)
        except ValueError:
            falhar(f"Resposta não JSON. HTTP {codigo}.")

    except (URLError, OSError, ValueError) as exc:
        falhar(f"Falha ao contactar {base}: {exc}")


def verificar(resultado, esperado, descricao, codigo_erro=None):
    codigo, dados = resultado

    if not isinstance(dados, dict):
        falhar(descricao + ": resposta inesperada.")

    if codigo != esperado or (
        codigo_erro is not None
        and dados.get("error") != codigo_erro
    ):
        print("HTTP recebido:", codigo)
        print("Erro:", dados.get("error"))
        print("Mensagem:", dados.get("message"))
        falhar(descricao)

    confirmar(True, descricao)
    return dados


def login(descricao, perfil):
    email = input(f"Email da conta {descricao}: ").strip()
    password = getpass(f"Palavra-passe da conta {descricao}: ")

    dados = verificar(
        pedido(
            AUTH,
            "/login",
            "POST",
            {"email": email, "password": password},
        ),
        200,
        f"Login da conta {descricao}",
    )

    del password

    token = dados.get("access_token")

    confirmar(
        isinstance(token, str) and bool(token),
        f"Token recebido para {descricao}",
    )

    conta = verificar(
        pedido(AUTH, "/me", token=token),
        200,
        f"Conta {descricao} pronta para utilização",
    )

    confirmar(
        conta.get("perfil") == perfil,
        f"Perfil da conta {descricao} é {perfil}",
    )

    return token, conta


def localizar_registo(dados):
    registos = dados.get("registos")

    if not isinstance(registos, list):
        falhar("A resposta não contém uma lista de registos.")

    for registo in registos:
        if (
            isinstance(registo, dict)
            and registo.get("data") == DATA
            and registo.get("aluno_id") == ALUNO
            and registo.get("turma_id") == TURMA
        ):
            return registo

    falhar("O registo de teste não foi encontrado.")


def principal():
    print("TESTE DE INTEGRAÇÃO DO DIÁRIO")
    print("Usar apenas as contas e o aluno de teste.")
    print("A edição atualizará a data de modificação do registo.\n")

    verificar(
        pedido(DIARIO, "/health"),
        200,
        "Aplicação Diário disponível",
    )

    verificar(
        pedido(DIARIO, "/ready"),
        200,
        "Ligação à base disponível",
    )

    verificar(
        pedido(DIARIO, ROTA),
        401,
        "Consulta profissional sem sessão bloqueada",
    )

    verificar(
        pedido(DIARIO, ROTA_ENCARREGADO),
        401,
        "Consulta do encarregado sem sessão bloqueada",
    )

    docente_token, docente = login("docente autor", "docente")
    encarregado_token, _ = login("encarregado", "encarregado")

    alunos = verificar(
        pedido(SCHOOL, "/me/alunos", token=encarregado_token),
        200,
        "Consulta dos educandos associados",
    )

    confirmar(
        any(
            item.get("id") == ALUNO
            and item.get("turma_id") == TURMA
            for item in alunos.get("alunos", [])
            if isinstance(item, dict)
        ),
        "Educando de teste associado ao encarregado",
    )

    dados = verificar(
        pedido(DIARIO, ROTA, token=docente_token),
        200,
        "Docente consulta o Diário",
    )

    original = localizar_registo(dados)

    confirmar(
        original.get("criado_por") == docente.get("id"),
        "Docente autenticado é o autor do registo",
    )

    payload = {
        "data": DATA,
        **{campo: original.get(campo, "") for campo in CAMPOS},
    }

    verificar(
        pedido(
            DIARIO,
            ROTA,
            "POST",
            payload,
            docente_token,
        ),
        409,
        "Criação duplicada bloqueada",
        "daily_record_already_exists",
    )

    verificar(
        pedido(
            DIARIO,
            ROTA,
            "POST",
            payload,
            encarregado_token,
        ),
        403,
        "Encarregado não pode criar registos",
        "forbidden",
    )

    verificar(
        pedido(DIARIO, ROTA, token=encarregado_token),
        403,
        "Encarregado não pode usar a consulta profissional",
        "forbidden",
    )

    verificar(
        pedido(
            DIARIO,
            f"/me/alunos/{ALUNO_EXEMPLO}/diario",
            token=encarregado_token,
        ),
        404,
        "Aluno de exemplo não associado recusado",
        "student_not_accessible",
    )

    verificar(
        pedido(
            DIARIO,
            f"/turmas/{TURMA_EXEMPLO}/alunos/{ALUNO}/diario",
            token=docente_token,
        ),
        404,
        "Turma de exemplo não acessível recusada",
        "resource_not_accessible",
    )

    verificar(
        pedido(DIARIO, ROTA_ENCARREGADO, token=docente_token),
        403,
        "Docente não pode usar a consulta dos encarregados",
        "forbidden",
    )

    verificar(
        pedido(
            DIARIO,
            ROTA + "/" + DATA,
            "PATCH",
            {"observacoes": original.get("observacoes", "")},
            encarregado_token,
        ),
        403,
        "Encarregado não pode editar",
        "forbidden",
    )

    campo = next(
        (
            nome
            for nome in CAMPOS
            if isinstance(original.get(nome), str)
            and original[nome].strip()
        ),
        None,
    )

    if campo is None:
        falhar("O registo não tem texto para testar a edição.")

    editado = verificar(
        pedido(
            DIARIO,
            ROTA + "/" + DATA,
            "PATCH",
            {campo: original[campo]},
            docente_token,
        ),
        200,
        "Docente autor pode editar",
    )

    confirmar(
        editado.get("atualizado_por") == docente["id"]
        and bool(editado.get("atualizado_em")),
        "Edição identifica a conta e a data de atualização",
    )

    dados = verificar(
        pedido(DIARIO, ROTA_ENCARREGADO, token=encarregado_token),
        200,
        "Encarregado consulta o Diário atualizado",
    )

    registo = localizar_registo(dados)

    confirmar(
        all(
            registo.get(nome) == original.get(nome)
            for nome in CAMPOS
        ),
        "Conteúdo dos campos mantém-se após o teste",
    )

    confirmar(
        "criado_por" not in registo
        and "atualizado_por" not in registo,
        "Identificadores das contas autoras não expostos ao encarregado",
    )

    confirmar(
        registo.get("atualizado_em") == editado.get("atualizado_em"),
        "Consulta do encarregado mostra a atualização guardada",
    )

    print(f"\nTESTE CONCLUÍDO - {aprovados} verificações aprovadas.")
    print("Nenhum novo registo foi criado no fluxo esperado.")
    print("O conteúdo foi mantido; a data de atualização foi renovada.")


if __name__ == "__main__":
    try:
        principal()
    except (KeyboardInterrupt, EOFError, GetPassWarning):
        print("\nTeste interrompido: credenciais não recolhidas em segurança.")
        sys.exit(1)