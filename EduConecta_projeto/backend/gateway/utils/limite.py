"""Utilitário: limite de pedidos por janela fixa de um minuto, em memória.

O estado vive no processo, por isso o gateway corre com um só worker
(ver o Dockerfile). Com vários workers cada um teria o seu contador e o
limite efetivo seria multiplicado.
"""

import time

JANELA = 60.0
_MAX_CHAVES = 10_000


class LimitadorJanelaFixa:
    def __init__(self, relogio=time.monotonic):
        self._relogio = relogio
        self._janelas = {}

    def tentar(self, chave, maximo):
        """Regista um pedido. Devolve (permitido, segundos_ate_nova_janela)."""
        agora = self._relogio()
        inicio, contagem = self._janelas.get(chave, (agora, 0))

        if agora - inicio >= JANELA:
            inicio, contagem = agora, 0

        if contagem >= maximo:
            return False, max(JANELA - (agora - inicio), 0.0)

        self._janelas[chave] = (inicio, contagem + 1)
        if len(self._janelas) > _MAX_CHAVES:
            self._limpar(agora)
        return True, 0.0

    def _limpar(self, agora):
        """Descarta as janelas já terminadas, para a memória não crescer sem fim."""
        self._janelas = {
            chave: (inicio, contagem)
            for chave, (inicio, contagem) in self._janelas.items()
            if agora - inicio < JANELA
        }
