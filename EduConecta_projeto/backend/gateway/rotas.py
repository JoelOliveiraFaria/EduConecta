"""Tabela de rotas do gateway: a única fonte de verdade sobre qual serviço
trata cada caminho.

Todos os caminhos públicos levam o prefixo /api, que é removido antes de o
pedido seguir para o serviço (os serviços não o conhecem).

Vários serviços partilham prefixos — por exemplo /turmas/{id} é do escolar,
mas /turmas/{id}/assiduidade é do assiduidade. `corresponder` resolve estas
colisões escolhendo a rota mais específica: em cada segmento, um literal
vence um parâmetro e um parâmetro vence um catch-all. Os testes em
tests/test_rotas.py fixam o resultado para todas as colisões conhecidas.

Padrões: `{nome}` casa exatamente um segmento; `{**resto}` casa zero ou mais
segmentos finais (por isso `/api/alunos/{**resto}` casa também `/api/alunos`).
"""

from dataclasses import dataclass, field

PREFIXO = "/api"

KB = 1024
MB = 1024 * 1024

# Limite de corpo das rotas que não definem o seu.
MAX_CORPO_PADRAO = 1 * MB

SERVICOS = ("auth", "escolar", "diario", "assiduidade", "comunicados", "notificacoes")

_LITERAL, _PARAMETRO, _CAUDA = 2, 1, 0


@dataclass(frozen=True)
class Rota:
    id: str
    caminho: str
    servico: str
    publica: bool = False
    limite: str = "api"
    max_corpo: int = MAX_CORPO_PADRAO
    caminho_servico: str | None = None
    segmentos: tuple = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        segmentos = []
        for texto in self.caminho.split("/")[1:]:
            if texto.startswith("{**"):
                segmentos.append((_CAUDA, texto))
            elif texto.startswith("{"):
                segmentos.append((_PARAMETRO, texto))
            else:
                segmentos.append((_LITERAL, texto))
        object.__setattr__(self, "segmentos", tuple(segmentos))


ROTAS = (
    # auth
    Rota("auth-login", "/api/login", "auth", publica=True, limite="login", max_corpo=16 * KB),
    Rota("auth-me", "/api/me", "auth", max_corpo=16 * KB),
    Rota("auth-password", "/api/password/{**resto}", "auth", max_corpo=16 * KB),
    Rota("auth-admin", "/api/admin/utilizadores/{**resto}", "auth", max_corpo=16 * KB),

    # escolar
    Rota("escolar-alunos", "/api/alunos/{**resto}", "escolar"),
    Rota("escolar-encarregados", "/api/encarregados/{**resto}", "escolar"),
    Rota("escolar-profissionais", "/api/profissionais/{**resto}", "escolar"),
    Rota("escolar-turmas", "/api/turmas", "escolar"),
    Rota("escolar-turma", "/api/turmas/{turma_id}", "escolar"),
    Rota("escolar-turma-alunos", "/api/turmas/{turma_id}/alunos", "escolar"),
    Rota("escolar-turma-profissionais", "/api/turmas/{turma_id}/profissionais/{**resto}", "escolar"),
    Rota("escolar-me-alunos", "/api/me/alunos", "escolar"),
    Rota("escolar-me-turmas", "/api/me/turmas/{**resto}", "escolar"),
    Rota("escolar-me-chat", "/api/me/chat/{**resto}", "escolar"),

    # diario
    Rota("diario-turma", "/api/turmas/{turma_id}/alunos/{aluno_id}/diario/{**resto}", "diario", max_corpo=16 * KB),
    Rota("diario-me", "/api/me/alunos/{aluno_id}/diario", "diario", max_corpo=16 * KB),

    # assiduidade
    Rota("assiduidade-turma", "/api/turmas/{turma_id}/assiduidade", "assiduidade", max_corpo=64 * KB),
    Rota("assiduidade-marcar", "/api/turmas/{turma_id}/alunos/{aluno_id}/assiduidade/{dia}", "assiduidade", max_corpo=64 * KB),
    Rota("assiduidade-aluno", "/api/alunos/{aluno_id}/assiduidade", "assiduidade", max_corpo=64 * KB),
    Rota("assiduidade-faltas", "/api/alunos/{aluno_id}/faltas/{**resto}", "assiduidade", max_corpo=6 * MB),

    # comunicados
    Rota("comunicados-turma", "/api/turmas/{turma_id}/comunicados/{**resto}", "comunicados", max_corpo=26 * MB),
    Rota("comunicados-conversas", "/api/conversas/{**resto}", "comunicados", max_corpo=26 * MB),

    # notificacoes
    Rota("notificacoes-me", "/api/me/notificacoes/{**resto}", "notificacoes", max_corpo=64 * KB),

    # Especificação OpenAPI de cada serviço (a página Swagger é servida pelo próprio gateway).
    *(
        Rota(f"openapi-{servico}", f"/api/openapi/{servico}.yaml", servico,
             publica=True, caminho_servico="/openapi.yaml")
        for servico in SERVICOS
    ),
)

# Maior corpo que alguma rota aceita; é o teto global da aplicação.
MAX_CORPO_GLOBAL = max(rota.max_corpo for rota in ROTAS)


def _pontuar(rota, segmentos):
    """Devolve a pontuação com que `rota` casa `segmentos`, ou None se não casar."""
    pontos = []
    for indice, (tipo, texto) in enumerate(rota.segmentos):
        if tipo == _CAUDA:
            pontos.append(_CAUDA)
            return pontos
        if indice >= len(segmentos):
            return None
        if tipo == _LITERAL:
            if segmentos[indice] != texto:
                return None
        elif not segmentos[indice]:
            return None
        pontos.append(tipo)
    return pontos if len(segmentos) == len(rota.segmentos) else None


def corresponder(caminho):
    """Devolve a rota mais específica que casa `caminho`, ou None.

    `caminho` já deve ter passado por `utils.caminhos.caminho_seguro` (sem
    segmentos vazios nem `.`/`..`). Uma barra final é ignorada.
    """
    segmentos = caminho.split("/")[1:]
    if segmentos and segmentos[-1] == "":
        segmentos.pop()

    melhor, melhores_pontos = None, None
    for rota in ROTAS:
        pontos = _pontuar(rota, segmentos)
        if pontos is not None and (melhores_pontos is None or pontos > melhores_pontos):
            melhor, melhores_pontos = rota, pontos
    return melhor
