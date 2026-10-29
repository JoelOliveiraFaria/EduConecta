import getpass
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = "http://comunicados:8000"
TURMA = "6ae0caf50852a73f69bac39e"
COMUNICADO = "6ae2320831d32dcfe98a3f6a"
FOTO = "6ae2320831d32dcfe98a3f6b"
RAIZ = f"/turmas/{TURMA}/comunicados/{COMUNICADO}"


def pedido(caminho, token=None, dados=None, headers=None, metodo=None):
    h = dict(headers or {})
    if token:
        h["Authorization"] = "Bearer " + token
    req = Request(caminho if caminho.startswith("http://") else BASE + caminho,
                  data=dados, headers=h, method=metodo)
    try:
        with urlopen(req, timeout=40) as r:
            return r.status, r.read(), r.headers
    except HTTPError as e:
        return e.code, e.read(), e.headers


def exigir(nome, resultado, estado):
    codigo, corpo, headers = resultado
    if codigo != estado:
        print(f"FALHOU — {nome}: HTTP {codigo}; esperado {estado}")
        print(corpo[:1500].decode("utf-8", errors="replace"))
        sys.exit(1)
    print(f"OK — {nome}: HTTP {codigo}")
    return corpo, headers


def login(perfil):
    print(f"\nCONTA: {perfil}")
    email = input("Email: ").strip()
    password = getpass.getpass("Palavra-passe: ")
    resultado = pedido("http://auth:8000/login", dados=json.dumps(
        {"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"})
    del password
    corpo, _ = exigir("início de sessão", resultado, 200)
    sessao = json.loads(corpo)
    permitidos = {"docente", "educadora"} if perfil == "docente" else {"encarregado"}
    if sessao["utilizador"]["perfil"] not in permitidos:
        raise RuntimeError("Perfil da conta incorreto.")
    return sessao["access_token"]


def multipart(campo, nome, tipo, dados):
    fronteira = uuid4().hex
    corpo = (f"--{fronteira}\r\nContent-Disposition: form-data; "
             f"name=\"{campo}\"; filename=\"{nome}\"\r\n"
             f"Content-Type: {tipo}\r\n\r\n").encode()
    corpo += dados + f"\r\n--{fronteira}--\r\n".encode()
    return corpo, {"Content-Type": "multipart/form-data; boundary=" + fronteira}


def executar():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg não encontrado: é necessário para gerar o vídeo de teste.")
    with tempfile.TemporaryDirectory() as pasta:
        caminho = Path(pasta) / "teste.mp4"
        resultado = subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
            "-i", "color=c=blue:s=320x240:r=10", "-t", "1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-an", str(caminho),
        ], capture_output=True, timeout=30)
        if resultado.returncode:
            raise RuntimeError("Não foi possível gerar o MP4: " +
                               resultado.stderr.decode(errors="replace")[:1000])
        video_bytes = caminho.read_bytes()
    print("OK — vídeo sintético de um segundo criado, sem dados pessoais.")
    docente = login("docente")
    encarregado = login("encarregado")

    exigir("listagem sem sessão recusada", pedido(RAIZ + "/fotografias"), 401)
    exigir("vídeos sem sessão recusados", pedido(RAIZ + "/videos"), 401)
    corpo, _ = exigir("listagem de fotografias", pedido(RAIZ + "/fotografias", docente), 200)
    if FOTO not in {x["id"] for x in json.loads(corpo)["fotografias"]}:
        raise RuntimeError("A fotografia de teste não apareceu na primeira página.")
    foto_url = RAIZ + "/fotografias/" + FOTO
    foto, _ = exigir("visualização da fotografia", pedido(foto_url, docente), 200)
    download, h = exigir("download da fotografia", pedido(foto_url + "?download=1", docente), 200)
    if foto != download or "attachment" not in h.get("Content-Disposition", ""):
        raise RuntimeError("Download da fotografia inconsistente.")
    exigir("fotografia sem sessão recusada", pedido(foto_url), 401)
    exigir("fotografia inexistente", pedido(RAIZ + "/fotografias/000000000000000000000000", docente), 404)
    exigir("comunicado inexistente", pedido(f"/turmas/{TURMA}/comunicados/000000000000000000000000/fotografias", docente), 404)

    corpo, cabecalhos = multipart("video", "falso.mp4", "video/mp4", b"isto nao e um video")
    exigir("ficheiro falso recusado", pedido(RAIZ + "/videos", docente, corpo, cabecalhos), 400)
    exigir("carregamento pelo encarregado recusado", pedido(RAIZ + "/videos", encarregado, corpo, cabecalhos), 403)
    corpo, cabecalhos = multipart("fotografia", "falso.jpg", "image/jpeg", b"teste")
    exigir("fotografia pelo encarregado recusada", pedido(RAIZ + "/fotografias", encarregado, corpo, cabecalhos), 403)

    print("\nEste passo guarda UM vídeo de teste no comunicado existente.")
    corpo, cabecalhos = multipart("video", "teste.mp4", "video/mp4", video_bytes)
    resposta, _ = exigir("carregamento do vídeo pela docente", pedido(RAIZ + "/videos", docente, corpo, cabecalhos), 201)
    vid = json.loads(resposta)["id"]
    video_url = RAIZ + "/videos/" + vid
    print("ID do vídeo:", vid)
    corpo, _ = exigir("listagem de vídeos", pedido(RAIZ + "/videos", docente), 200)
    if vid not in {x["id"] for x in json.loads(corpo)["videos"]}:
        raise RuntimeError("O vídeo criado não aparece na listagem.")
    dados, _ = exigir("leitura do vídeo", pedido(video_url, docente), 200)
    if hashlib.sha256(dados).digest() != hashlib.sha256(video_bytes).digest():
        raise RuntimeError("O vídeo recuperado difere do original.")
    dados, h = exigir("download do vídeo", pedido(video_url + "?download=1", docente), 200)
    if dados != video_bytes or "attachment" not in h.get("Content-Disposition", ""):
        raise RuntimeError("Download do vídeo inconsistente.")
    dados, _ = exigir("leitura parcial do vídeo", pedido(video_url, docente, headers={"Range": "bytes=0-15"}), 206)
    if dados != video_bytes[:16]:
        raise RuntimeError("Leitura parcial inconsistente.")
    exigir("vídeo sem sessão recusado", pedido(video_url), 401)

    corpo, _ = exigir("educandos do encarregado", pedido("http://escolar:8000/me/alunos", encarregado), 200)
    alunos = json.loads(corpo).get("alunos", [])
    associado = any(isinstance(a, dict) and a.get("turma_id") == TURMA for a in alunos)
    esperado = 200 if associado else 404
    for caminho in (RAIZ + "/fotografias", foto_url, foto_url + "?download=1",
                    RAIZ + "/videos", video_url, video_url + "?download=1"):
        exigir("leitura pelo encarregado: " + caminho.rsplit("/", 1)[-1],
               pedido(caminho, encarregado), esperado)
    if associado:
        print("\nEncarregado associado: leitura permitida. Falta uma terceira conta sem ligação para testar isolamento entre utilizadores.")
    else:
        print("\nEncarregado sem associação à turma: leitura recusada. Falta testar leitura com um encarregado associado.")
    print("\nOK — todos os testes executados passaram. Não foram criados novos comunicados.")
    print("Foi guardado um vídeo sintético. Não foram apagados dados existentes.")


if __name__ == "__main__":
    try:
        executar()
    except (URLError, TimeoutError, OSError, ValueError, KeyError,
            RuntimeError, subprocess.SubprocessError) as exc:
        print("\nTESTE INTERROMPIDO:", exc)
        sys.exit(1)