"""Utilitário: verificação ativa da saúde dos serviços.

De 10 em 10 segundos o gateway pergunta `/health` a cada serviço. Um serviço
que falhe 3 vezes seguidas deixa de receber pedidos: o gateway responde logo
503 em vez de esperar pelo timeout, e volta a encaminhar assim que um
`/health` correr bem.

O `/health` dos serviços só diz que o processo está vivo; se a base de dados
está disponível vê-se no `/ready` (ver `GET /api/ready`).
"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

LIMIAR_FALHAS = 3
INTERVALO = 10.0
TIMEOUT = 5.0


class MonitorSaude:
    def __init__(self, servicos, limiar=LIMIAR_FALHAS, intervalo=INTERVALO):
        self._falhas = {servico: 0 for servico in servicos}
        self._limiar = limiar
        self._intervalo = intervalo

    def saudavel(self, servico):
        return self._falhas[servico] < self._limiar

    async def verificar(self, cliente, upstreams):
        """Faz uma ronda de verificações, em paralelo."""
        await asyncio.gather(*(
            self._verificar_um(cliente, servico, upstreams[servico]) for servico in self._falhas
        ))

    async def _verificar_um(self, cliente, servico, base):
        antes = self.saudavel(servico)
        try:
            resposta = await cliente.get(f"{base}/health", timeout=TIMEOUT)
            bem = resposta.status_code == 200
        except httpx.HTTPError:
            bem = False

        self._falhas[servico] = 0 if bem else self._falhas[servico] + 1

        agora = self.saudavel(servico)
        if antes and not agora:
            logger.warning("Serviço %s marcado como indisponível.", servico)
        elif not antes and agora:
            logger.info("Serviço %s voltou a responder.", servico)

    async def correr(self, obter_cliente, upstreams):
        """Tarefa de fundo: repete as rondas até o gateway parar."""
        while True:
            await self.verificar(obter_cliente(), upstreams)
            await asyncio.sleep(self._intervalo)
