"""Model: coleção `auditoria` — regista eventos que o consumidor processa mas
que não geram notificação para ninguém (ex: aluno.eliminado — não há
utilizador nenhum a avisar). Serve só de prova de que o evento chegou e foi
processado, não é lido por nenhuma rota HTTP.
"""

from datetime import datetime, timezone

from db import auditoria


def registar(tipo, dados):
    auditoria.insert_one({
        "tipo": tipo,
        "dados": dados,
        "processado_em": datetime.now(timezone.utc),
    })
