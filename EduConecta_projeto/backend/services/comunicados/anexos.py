import json
import math
import subprocess
import tempfile
from io import BytesIO

from bson import ObjectId
from flask import g, jsonify, request, send_file
from gridfs import GridFS
from gridfs.errors import NoFile, CorruptGridFile
from pymongo.errors import PyMongoError


MAX_VIDEO = 25 * 1024 * 1024
MAX_FOTO = 5 * 1024 * 1024
BASE = "/turmas/<turma_id>/comunicados/<comunicado_id>"


def analisar_mp4(caminho):
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


def instalar_anexos(app, database, verificar_acesso, erro):
    if app.extensions.get("educonecta_anexos"):
        return
    app.config["MAX_CONTENT_LENGTH"] = 26 * 1024 * 1024
    buckets = {tipo: GridFS(database, collection=tipo)
               for tipo in ("fotografias", "videos")}

    def autorizar(turma_id, comunicado_id, publicar=False):
        falha = verificar_acesso(turma_id, publicar=publicar)
        if falha is not None:
            return None, falha
        if not ObjectId.is_valid(comunicado_id):
            return None, erro("invalid_notice_id", "Identificador inválido.", 400)
        cid = str(ObjectId(comunicado_id))
        filtro = {"_id": ObjectId(cid), "turma_id": g.turma_id}
        if publicar:
            filtro["criado_por"] = g.utilizador_id
        try:
            doc = database["comunicados"].find_one(filtro, {"_id": 1})
        except PyMongoError:
            return None, erro("database_unavailable", "Base de dados indisponível.", 503)
        if doc is None:
            return None, erro("notice_not_accessible", "Comunicado não acessível.", 404)
        return cid, None

    def listar(turma_id, comunicado_id, tipo):
        cid, falha = autorizar(turma_id, comunicado_id)
        if falha is not None:
            return falha
        if (set(request.args) - {"antes_de"}
                or len(request.args.getlist("antes_de")) > 1):
            return erro("invalid_query", "Envia apenas um antes_de opcional.", 400)
        filtro = {"metadata.turma_id": g.turma_id,
                  "metadata.comunicado_id": cid}
        cursor = request.args.get("antes_de")
        if cursor is not None:
            if not ObjectId.is_valid(cursor):
                return erro("invalid_cursor", "Cursor inválido.", 400)
            filtro["_id"] = {"$lt": ObjectId(cursor)}
        try:
            docs = list(database[tipo + ".files"].find(
                filtro, {"_id": 1, "length": 1, "metadata": 1}
            ).sort("_id", -1).limit(21))
        except PyMongoError:
            return erro("database_unavailable", "Não foi possível listar os anexos.", 503)
        pagina = docs[:20]
        itens = []
        for doc in pagina:
            fid = str(doc["_id"])
            url = f"/turmas/{g.turma_id}/comunicados/{cid}/{tipo}/{fid}"
            meta = doc.get("metadata", {})
            item = {"id": fid, "tamanho_bytes": doc["length"],
                    "tipo": "image/jpeg" if tipo == "fotografias" else "video/mp4",
                    "url": url, "url_download": url + "?download=1"}
            for campo in ("largura", "altura", "duracao_segundos", "tem_audio"):
                if campo in meta:
                    item[campo] = meta[campo]
            itens.append(item)
        return jsonify({"comunicado_id": cid, tipo: itens,
                        "quantidade": len(itens), "limite": 20,
                        "tem_mais": len(docs) > 20,
                        "proximo_cursor": str(pagina[-1]["_id"])
                        if len(docs) > 20 else None}), 200

    def obter(turma_id, comunicado_id, anexo_id, tipo):
        cid, falha = autorizar(turma_id, comunicado_id)
        if falha is not None:
            return falha
        if not ObjectId.is_valid(anexo_id):
            return erro("invalid_attachment_id", "Identificador inválido.", 400)
        if (set(request.args) - {"download"}
                or len(request.args.getlist("download")) > 1
                or request.args.get("download") not in {None, "1"}):
            return erro("invalid_query", "Apenas download=1 é permitido.", 400)
        limite = MAX_FOTO if tipo == "fotografias" else MAX_VIDEO
        try:
            ficheiro = buckets[tipo].find_one({
                "_id": ObjectId(anexo_id), "metadata.turma_id": g.turma_id,
                "metadata.comunicado_id": cid,
            })
            if ficheiro is None:
                return erro("attachment_not_accessible", "Anexo não acessível.", 404)
            with ficheiro:
                if not 0 < ficheiro.length <= limite:
                    return erro("attachment_unavailable", "Tamanho inesperado.", 503)
                dados = ficheiro.read(limite + 1)
                if len(dados) != ficheiro.length:
                    return erro("attachment_unavailable", "Anexo incompleto.", 503)
        except (NoFile, CorruptGridFile, PyMongoError):
            return erro("attachment_unavailable", "Não foi possível ler o anexo.", 503)
        extensao = "jpg" if tipo == "fotografias" else "mp4"
        resposta = send_file(
            BytesIO(dados),
            mimetype="image/jpeg" if tipo == "fotografias" else "video/mp4",
            download_name=f"educonecta-{ObjectId(anexo_id)}.{extensao}",
            as_attachment=request.args.get("download") == "1",
            conditional=True, etag=False, max_age=0,
        )
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        return resposta

    def carregar_video(turma_id, comunicado_id):
        cid, falha = autorizar(turma_id, comunicado_id, publicar=True)
        if falha is not None:
            return falha
        if request.mimetype != "multipart/form-data":
            return erro("unsupported_media_type", "Envia multipart/form-data.", 415)
        if (request.form or set(request.files) != {"video"}
                or len(request.files.getlist("video")) != 1):
            return erro("invalid_fields", "Envia apenas um ficheiro no campo video.", 400)
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4", mode="w+b") as tmp:
                tamanho = 0
                while True:
                    bloco = request.files["video"].stream.read(64 * 1024)
                    if not bloco:
                        break
                    tamanho += len(bloco)
                    if tamanho > MAX_VIDEO:
                        return erro("file_too_large", "O vídeo deve ter até 25 MB.", 413)
                    tmp.write(bloco)
                if tamanho == 0:
                    return erro("empty_file", "O vídeo está vazio.", 400)
                tmp.flush()
                try:
                    info = analisar_mp4(tmp.name)
                except subprocess.TimeoutExpired:
                    return erro("video_analysis_timeout", "Análise excedeu dez segundos.", 400)
                except (subprocess.CalledProcessError, ValueError, TypeError,
                        KeyError, AttributeError, OverflowError):
                    return erro("invalid_video", "Envia MP4 H.264, com áudio AAC opcional, sem pistas adicionais.", 400)
                tmp.seek(0)
                vid = ObjectId()
                nome = f"educonecta-{vid}.mp4"
                try:
                    buckets["videos"].put(
                        tmp, _id=vid, filename=nome,
                        metadata={"comunicado_id": cid, "turma_id": g.turma_id,
                                  "criado_por": g.utilizador_id,
                                  "tipo": "video/mp4", **info},
                    )
                except PyMongoError:
                    return erro("database_unavailable", "Carregamento não confirmado. Não repitas automaticamente.", 503)
        except OSError:
            return erro("video_processing_unavailable", "Ferramenta ou armazenamento temporário indisponível.", 503)
        return jsonify({"id": str(vid), "nome": nome, "tipo": "video/mp4",
                        "comunicado_id": cid, "turma_id": g.turma_id,
                        "tamanho_bytes": tamanho, **info}), 201

    def registar(caminho, metodo, endpoint, funcao):
        existentes = [r for r in app.url_map.iter_rules()
                      if r.rule == caminho and metodo in r.methods]
        if len(existentes) > 1:
            raise RuntimeError("Rotas duplicadas: " + caminho)
        if not existentes:
            app.add_url_rule(caminho, endpoint, funcao, methods=[metodo])

    def listar_fotos(turma_id, comunicado_id):
        return listar(turma_id, comunicado_id, "fotografias")

    def listar_videos(turma_id, comunicado_id):
        return listar(turma_id, comunicado_id, "videos")

    def obter_foto(turma_id, comunicado_id, fotografia_id):
        return obter(turma_id, comunicado_id, fotografia_id, "fotografias")

    def obter_video(turma_id, comunicado_id, video_id):
        return obter(turma_id, comunicado_id, video_id, "videos")

    registar(BASE + "/fotografias", "GET", "anexos_listar_fotos", listar_fotos)
    registar(BASE + "/fotografias/<fotografia_id>", "GET", "anexos_obter_foto", obter_foto)
    registar(BASE + "/videos", "GET", "anexos_listar_videos", listar_videos)
    registar(BASE + "/videos/<video_id>", "GET", "anexos_obter_video", obter_video)
    registar(BASE + "/videos", "POST", "anexos_carregar_video", carregar_video)
    app.extensions["educonecta_anexos"] = True