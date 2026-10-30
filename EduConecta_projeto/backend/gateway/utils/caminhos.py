"""Utilitário: validação do caminho do pedido antes de o casar com as rotas.

O gateway só encaminha caminhos "limpos". Recusar tudo o que possa ser
reescrito a caminho do serviço (segmentos `.`/`..`, barras repetidas, barras
e pontos codificados) impede um pedido como `/api/alunos/../internal/...`
de contornar a tabela de rotas e chegar a uma rota interna. Nenhum
identificador desta API (ObjectId, datas) precisa destes caracteres.
"""

_CODIFICADOS_PROIBIDOS = ("%2e", "%2f", "%5c", "%00")


def caminho_seguro(bruto, decodificado):
    """True se o caminho pode ser casado e encaminhado.

    `bruto` é o caminho tal como o cliente o enviou (ainda codificado) e
    `decodificado` o mesmo caminho já descodificado pelo servidor ASGI.
    """
    minusculas = bruto.lower()
    if any(codigo in minusculas for codigo in _CODIFICADOS_PROIBIDOS):
        return False
    if "\\" in bruto or "\x00" in decodificado or "\\" in decodificado:
        return False

    segmentos = decodificado.split("/")[1:]
    if segmentos and segmentos[-1] == "":
        segmentos.pop()
    return all(segmento not in ("", ".", "..") for segmento in segmentos)
