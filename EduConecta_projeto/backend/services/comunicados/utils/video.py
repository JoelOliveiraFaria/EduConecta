"""Utilitário: valida um ficheiro MP4 carregado usando o ffprobe (do ffmpeg),
sem nunca o reencodar — só inspeciona o contentor e recusa o que não bate
com um MP4 "normal" de telemóvel (H.264 + AAC opcional, uma única pista de
vídeo). Ao contrário das fotografias, não há conversão aqui: um vídeo que
passe nesta validação é guardado tal como foi recebido.
"""

import json
import math
import subprocess


def analisar_mp4(caminho):
    """Inspeciona o MP4 em `caminho` e devolve os seus metadados, ou levanta
    ValueError/subprocess.CalledProcessError/TimeoutExpired se algo não for
    permitido (apanhado pelo controller, que devolve um 400 genérico sem
    expor ao cliente qual verificação exata falhou).

    Verificações, por ordem:
      - o `ffprobe` corre com -protocol_whitelist file (não aceita URLs
        nem outros protocolos, só o ficheiro local) e timeout de 10s;
      - o `major_brand` do contentor tem de ser um dos valores MP4/MOV
        conhecidos — recusa contentores disfarçados de .mp4;
      - duração finita e positiva;
      - exatamente uma pista de vídeo, no máximo uma de áudio, e nenhuma
        pista extra (legendas, metadados, outra pista de vídeo escondida);
      - vídeo tem de ser H.264 e não pode ser uma "imagem anexada"
        (capa/thumbnail embutida, sinalizada por `attached_pic`);
      - áudio, se existir, tem de ser AAC;
      - largura/altura válidas.
    """
    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-protocol_whitelist", "file",
         "-f", "mov", "-show_entries",
         "format=duration:format_tags=major_brand:"
         "stream=codec_type,codec_name,width,height:"
         "stream_disposition=attached_pic", "-of", "json", caminho],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, timeout=10, check=True,
    )
    dados = json.loads(resultado.stdout)
    formato = dados["format"]
    streams = dados["streams"]
    marcas = {"isom", "iso2", "iso3", "iso4", "iso5", "iso6",
              "mp41", "mp42", "avc1", "M4V ", "MSNV"}
    if formato.get("tags", {}).get("major_brand") not in marcas:
        raise ValueError("Contentor MP4 não suportado.")
    duracao = float(formato.get("duration", "nan"))
    if not math.isfinite(duracao) or duracao <= 0:
        raise ValueError("Duração inválida.")
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if len(video) != 1 or len(audio) > 1 or len(streams) != 1 + len(audio):
        raise ValueError("Pistas não suportadas.")
    v = video[0]
    if (v.get("codec_name") != "h264"
            or v.get("disposition", {}).get("attached_pic", 0)):
        raise ValueError("É necessário vídeo H.264.")
    if audio and audio[0].get("codec_name") != "aac":
        raise ValueError("É necessário áudio AAC.")
    largura, altura = v.get("width"), v.get("height")
    if (not isinstance(largura, int) or not isinstance(altura, int)
            or largura <= 0 or altura <= 0):
        raise ValueError("Dimensões inválidas.")
    return {"duracao_segundos": round(duracao, 3), "largura": largura,
            "altura": altura, "tem_audio": bool(audio)}
