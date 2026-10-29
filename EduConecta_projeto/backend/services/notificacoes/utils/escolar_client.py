"""Utilitário: chama o endpoint interno do serviço `escolar` que resolve
quem deve ser avisado por um evento de uma turma (profissionais atribuídos
+ encarregados de educação dos seus alunos).

Usa uma chave partilhada (`X-Internal-Key`), não um token de utilizador —
quem chama é o consumidor RabbitMQ deste serviço, a processar uma mensagem
em segundo plano, sem nenhuma sessão HTTP associada (ver utils/consumidor.py).
"""

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def destinatarios_da_turma(turma_id):
    """Devolve (dados, None) com profissionais_utilizador_ids e
    encarregados_utilizador_ids, ou (None, motivo) se não for possível
    consultar — quem chama decide se ignora o evento."""
    pedido = Request(
        f"http://escolar:8000/internal/turmas/{turma_id}/destinatarios",
        headers={
            "X-Internal-Key": os.environ.get("INTERNAL_SERVICE_KEY", ""),
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(pedido, timeout=5) as resposta:
            dados = json.load(resposta)
        if not isinstance(dados, dict):
            raise ValueError()
        return dados, None
    except HTTPError as exc:
        logger.warning(
            "escolar devolveu %s a resolver destinatários da turma %s.", exc.code, turma_id
        )
        exc.close()
        return None, "resource_not_accessible"
    except (URLError, OSError, TimeoutError, ValueError):
        logger.warning(
            "Não foi possível contactar o escolar para resolver destinatários da turma %s.",
            turma_id,
        )
        return None, "dependency_unavailable"
