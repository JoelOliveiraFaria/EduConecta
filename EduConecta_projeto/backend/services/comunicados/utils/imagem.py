"""Utilitário: normaliza qualquer fotografia carregada para um JPEG seguro e
previsível, antes de ir para o GridFS (ver models/anexo.py).

Fazer isto sempre, em vez de guardar o ficheiro como foi enviado, resolve de
uma vez: formatos variados, orientação errada por falta de rotação EXIF,
canal alfa que o JPEG não suporta, bombas de descompressão (imagens com
dimensões enormes escondidas num ficheiro pequeno) e metadados EXIF
sensíveis (localização, modelo do aparelho) que não queremos guardar.
"""

from io import BytesIO

from PIL import Image, ImageOps

from db import FORMATOS_FOTOGRAFIA, MAX_FOTOGRAFIA_BYTES, MAX_FOTOGRAFIA_PIXEIS


def preparar_fotografia(conteudo):
    """Valida e converte os bytes recebidos numa fotografia JPEG pronta a guardar.

    Levanta ValueError (apanhado pelo controller, junto com os erros do
    próprio Pillow) em qualquer passo que falhe. Devolve
    (bytes_jpeg, largura, altura) no sucesso.
    """
    with Image.open(BytesIO(conteudo)) as imagem:
        if imagem.format not in FORMATOS_FOTOGRAFIA:
            raise ValueError("Formato não permitido.")

        largura, altura = imagem.size

        # Verificado antes de imagem.load(): recusar aqui evita decodificar
        # (e gastar memória com) uma "bomba de descompressão" — um ficheiro
        # pequeno que descomprime para uma imagem gigantesca.
        if (
            largura <= 0
            or altura <= 0
            or largura * altura > MAX_FOTOGRAFIA_PIXEIS
        ):
            raise ValueError("Dimensões não permitidas.")

        if getattr(imagem, "is_animated", False):
            raise ValueError("Imagens animadas não são permitidas.")

        imagem.load()
        # As câmaras guardam a orientação real num campo EXIF em vez de
        # rodarem o pixel data; exif_transpose aplica essa rotação de facto,
        # para a imagem não aparecer de lado/invertida a quem a vir depois.
        orientada = ImageOps.exif_transpose(imagem)

        try:
            # PNG/WEBP podem ter canal alfa (transparência), que o JPEG não
            # suporta — compõe-se sobre um fundo branco antes de converter,
            # em vez de deixar o Pillow decidir uma cor por omissão.
            rgba = orientada.convert("RGBA")

            try:
                limpa = Image.new("RGB", rgba.size, "white")

                try:
                    mascara = rgba.getchannel("A")

                    try:
                        limpa.paste(rgba, mask=mascara)
                    finally:
                        mascara.close()

                    # Reencodar para JPEG aqui, e só aqui, descarta todo o
                    # EXIF original (incluindo GPS/modelo do aparelho) — o
                    # ficheiro final não tem metadados do autor da fotografia.
                    with BytesIO() as saida:
                        limpa.save(
                            saida,
                            format="JPEG",
                            quality=90,
                        )
                        resultado = saida.getvalue()

                    largura, altura = limpa.size

                finally:
                    limpa.close()

            finally:
                rgba.close()

        finally:
            orientada.close()

    if len(resultado) > MAX_FOTOGRAFIA_BYTES:
        raise ValueError("Imagem convertida demasiado grande.")

    return resultado, largura, altura
