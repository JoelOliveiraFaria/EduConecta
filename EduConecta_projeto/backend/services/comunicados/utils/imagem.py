from io import BytesIO

from PIL import Image, ImageOps

from db import FORMATOS_FOTOGRAFIA, MAX_FOTOGRAFIA_BYTES, MAX_FOTOGRAFIA_PIXEIS


def preparar_fotografia(conteudo):
    with Image.open(BytesIO(conteudo)) as imagem:
        if imagem.format not in FORMATOS_FOTOGRAFIA:
            raise ValueError("Formato não permitido.")

        largura, altura = imagem.size

        if (
            largura <= 0
            or altura <= 0
            or largura * altura > MAX_FOTOGRAFIA_PIXEIS
        ):
            raise ValueError("Dimensões não permitidas.")

        if getattr(imagem, "is_animated", False):
            raise ValueError("Imagens animadas não são permitidas.")

        imagem.load()
        orientada = ImageOps.exif_transpose(imagem)

        try:
            rgba = orientada.convert("RGBA")

            try:
                limpa = Image.new("RGB", rgba.size, "white")

                try:
                    mascara = rgba.getchannel("A")

                    try:
                        limpa.paste(rgba, mask=mascara)
                    finally:
                        mascara.close()

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
