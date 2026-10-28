import getpass
import json
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://assiduidade:8000"


def pedir(url, token=None, dados=None, metodo=None):
    headers = {"Accept": "application/json"}
    corpo = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if dados is not None:
        headers["Content-Type"] = "application/json"
        corpo = json.dumps(dados).encode()
    req = Request(url if url.startswith("http://") else BASE + url,
                  data=corpo, headers=headers, method=metodo)
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except HTTPError as e:
        texto = e.read().decode(errors="replace")
        try:
            texto = json.loads(texto)
        except ValueError:
            pass
        return e.code, texto


def exigir(nome, resposta, esperado):
    codigo, dados = resposta
    if codigo != esperado:
        raise RuntimeError(f"{nome}: HTTP {codigo}; esperado {esperado}; {dados}")
    print(f"OK — {nome}: HTTP {codigo}")
    return dados


def login(perfil):
    print("\nCONTA:", perfil)
    email = input("Email: ").strip()
    password = getpass.getpass("Palavra-passe: ")
    s = exigir("início de sessão", pedir("http://auth:8000/login", dados={
        "email": email, "password": password,
    }), 200)
    del password
    permitidos = {"docente", "educadora"} if perfil == "docente" else {"encarregado"}
    if s["utilizador"]["perfil"] not in permitidos:
        raise RuntimeError("Perfil da conta incorreto.")
    return s["access_token"]


def executar():
    exigir("disponibilidade da assiduidade", pedir("/ready"), 200)
    docente = login("docente")
    encarregado = login("encarregado")
    turmas = exigir("turmas da docente", pedir("http://escolar:8000/me/turmas", docente), 200)["turmas"]
    alunos_pai = exigir("educandos do encarregado", pedir("http://escolar:8000/me/alunos", encarregado), 200)["alunos"]
    ids = {a["id"] for a in alunos_pai}
    escolha = None
    for turma in turmas:
        dados = exigir("alunos da turma", pedir(f"http://escolar:8000/me/turmas/{turma['id']}/alunos", docente), 200)
        for aluno in dados["alunos"]:
            if aluno["id"] in ids:
                escolha = (turma["id"], aluno["id"])
                break
        if escolha:
            break
    if not escolha:
        raise RuntimeError("Não foi encontrado um aluno comum. Não foram feitas marcações.")
    tid, aid = escolha
    print("\nTurma de teste:", tid)
    print("Aluno de teste:", aid)
    dia = input("Data AAAA-MM-DD (Enter = hoje em UTC): ").strip()
    dia = dia or datetime.now(timezone.utc).date().isoformat()
    turma_url = f"/turmas/{tid}/assiduidade"
    consulta = turma_url + "?data=" + dia
    escrita = f"/turmas/{tid}/alunos/{aid}/assiduidade/{dia}"
    leitura = f"/alunos/{aid}/assiduidade?inicio={dia}&fim={dia}"
    exigir("consulta sem sessão recusada", pedir(consulta), 401)
    exigir("encarregado não consulta a turma inteira", pedir(consulta, encarregado), 403)
    exigir("turma inexistente recusada", pedir("/turmas/000000000000000000000000/assiduidade?data=" + dia, docente), 404)
    exigir("data impossível recusada", pedir(turma_url + "?data=2026-02-30", docente), 400)
    dados = exigir("consulta diária da docente", pedir(consulta, docente), 200)
    original = next(a for a in dados["alunos"] if a["aluno_id"] == aid)
    if not original["editavel"]:
        raise RuntimeError("Marcação pertence a outra turma; não foram feitas alterações.")
    exigir("encarregado consulta o educando", pedir(leitura, encarregado), 200)
    exigir("docente não usa consulta reservada ao encarregado", pedir(leitura, docente), 403)
    exigir("educando inexistente recusado", pedir(f"/alunos/000000000000000000000000/assiduidade?inicio={dia}&fim={dia}", encarregado), 404)
    payload = {"estado": "presente", "versao": original["versao"]}
    exigir("marcação sem sessão recusada", pedir(escrita, dados=payload, metodo="PUT"), 401)
    exigir("encarregado não pode marcar", pedir(escrita, encarregado, payload, "PUT"), 403)
    exigir("estado inválido recusado", pedir(escrita, docente, {"estado": "invalido", "versao": original["versao"]}, "PUT"), 400)
    print("\nO teste altera temporariamente a marcação. Usa APENAS um aluno de teste.")
    print("Estado atual:", original["estado"])
    print("No fim tenta repor esse estado. A versão, a hora e o autor ficam atualizados.")
    print("Se não existia registo, fica um registo por_marcar; não são apagados dados.")
    if input("Escreve TESTAR para continuar: ").strip() != "TESTAR":
        print("Cancelado sem marcações.")
        return
    versao = original["versao"]
    alterado = False
    try:
        doc = exigir("marcar presença", pedir(escrita, docente, {"estado": "presente", "versao": versao}, "PUT"), 200)
        alterado = True
        versao = doc["versao"]
        if doc["estado"] != "presente":
            raise RuntimeError("Estado inesperado após marcar presença.")
        exigir("versão antiga recusada", pedir(escrita, docente, {"estado": "falta", "versao": original["versao"]}, "PUT"), 409)
        doc = exigir("corrigir para falta", pedir(escrita, docente, {"estado": "falta", "versao": versao}, "PUT"), 200)
        versao = doc["versao"]
        registos = exigir("encarregado vê a falta", pedir(leitura, encarregado), 200)["registos"]
        if len(registos) != 1 or registos[0]["estado"] != "falta":
            raise RuntimeError("Consulta do encarregado inconsistente.")
    finally:
        if alterado:
            resposta = pedir(escrita, docente, {"estado": original["estado"], "versao": versao}, "PUT")
            if resposta[0] != 200:
                print("ATENÇÃO — estado anterior não reposto:", resposta)
                raise RuntimeError("Consulta a marcação antes de corrigir manualmente.")
            print("OK — estado anterior reposto:", resposta[1]["estado"])
    print("\nOK — testes do microserviço independente de assiduidade passaram.")
    print("Falta testar outra conta sem ligação, transferências e concorrência real entre clientes.")


if __name__ == "__main__":
    try:
        executar()
    except (RuntimeError, ValueError, KeyError, StopIteration, URLError, OSError, TimeoutError) as exc:
        print("\nTESTE INTERROMPIDO:", exc)
        sys.exit(1)