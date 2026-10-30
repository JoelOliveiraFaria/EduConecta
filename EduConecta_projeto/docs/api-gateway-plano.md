# API Gateway — plano de implementação

Documento para aprovação antes de começar a implementar (mesmo formato das Fases 1 e 2).

---

## 1. Ponto de partida

Hoje **não existe gateway**. A arquitetura descrita no README (YARP à frente dos serviços, a validar o JWT) ainda não está implementada. O que existe no código:

- **6 serviços, 6 portas expostas** no `compose.yaml`: escolar `5001`, auth `5002`, diario `5003`, comunicados `5004`, assiduidade `5005`, notificacoes `5006`. Quem chama a API tem de saber qual serviço trata cada rota.
- **Cada serviço autentica sozinho.** Em todos os pedidos, o serviço chama `GET /me` no auth com o `Authorization` recebido (`utils/http_client.py`, `utils/auth_client.py`). Um pedido ao diário gera, no mínimo, uma segunda chamada HTTP ao auth.
- **O `/me` valida mais do que a assinatura do token:** confirma que a conta existe, que `estado == "ativo"` e que não há `deve_alterar_password` pendente (`auth_controller.py`).
- **O JWT** é HS256, dura 15 minutos e tem `iss=educonecta-auth`, `aud=educonecta-api` e `jti`. O segredo `JWT_SECRET_KEY` só existe no auth.
- **Os serviços falam entre si por nome** (`http://auth:8000`, `http://escolar:8000`) e reencaminham o token do cliente. Este tráfego interno fica fora do gateway.
- **Não encontrei** CORS nem limite de tentativas (rate limiting) em nenhum serviço.
- **Não há frontend no repositório.** Os únicos clientes são os scripts de `testes_manuais/`, que apontam diretamente para `127.0.0.1:5001–5004`.

### Tensão com o README
O README fixa **YARP (.NET)**, mas todos os serviços são **Python** (Flask e Quart). O gateway seria o único componente .NET. O SDK .NET 8.0.302 já está instalado nesta máquina.

---

## 2. Decisão proposta: YARP

Implementar o gateway com **YARP** num projeto ASP.NET Core mínimo (`backend/gateway/`), porque é o que a arquitetura entregue (README e diagrama) especifica. A configuração é quase toda declarativa (`appsettings.json`), com poucas dezenas de linhas de código.

Se a equipa preferir não introduzir .NET, o equivalente é Traefik ou Nginx. O plano abaixo mantém-se, mas a secção 5 (validação de JWT) passaria a ser configuração em vez de código.

---

## 3. O que muda: antes e depois

| Aspeto | Hoje | Com gateway |
|---|---|---|
| Entrada da API | 6 portas, uma por serviço | **1 porta** (`8080`); os serviços deixam de estar publicados |
| Quem decide o serviço de cada rota | O cliente | O gateway, pela tabela de rotas |
| Pedido sem token ou com token inválido | Chega ao serviço, que chama o auth e só depois recusa | **Recusado no gateway** (401), sem tocar nos serviços |
| Verificação de conta ativa e perfil | Em cada serviço, via `/me` | **Igual** (mantém-se como segunda barreira) |
| Rotas `/internal/*` do escolar | Acessíveis em `localhost:5001` (protegidas só por `X-Internal-Key`) | **Sem rota no gateway**, e a porta 5001 fecha |
| CORS | Inexistente | No gateway (só em desenvolvimento) |
| Limite de tentativas de login | Inexistente | No gateway |
| Limites de upload e timeouts | Dispersos pelos serviços | Alinhados por rota no gateway |
| `/health`, `/ready`, `/docs` | Repetidos em cada serviço | Gateway tem o seu `/health`; docs agregadas por serviço |
| Código dos serviços | — | **Não muda** nas fases 1 a 3 |
| Chamadas serviço a serviço | Diretas | **Diretas** (não passam pelo gateway) |

---

## 4. Tabela de rotas

O gateway expõe tudo sob `/api` e remove o prefixo antes de encaminhar (`PathRemovePrefix`), por isso os serviços ficam como estão. Os URLs não incluem o nome do serviço, para o cliente não depender da decomposição.

O ponto delicado é que **várias rotas partilham prefixos entre serviços**. Por exemplo, `/turmas/{id}` é do escolar, mas `/turmas/{id}/assiduidade` é do assiduidade. O ASP.NET dá prioridade a segmentos literais sobre parâmetros e a parâmetros sobre `catch-all`, o que resolve isto sem ordenar à mão. Ainda assim, a tabela tem de ter um teste (secção 7).

| Serviço | Rotas (todas com prefixo `/api`) |
|---|---|
| **auth** | `POST /login`, `GET /me` (exato), `POST /password/alterar`, `/admin/utilizadores/**` |
| **escolar** | `/alunos` e `/alunos/{id}` (+ `/turma`, `/encarregados/**`), `/encarregados/**`, `/profissionais/**`, `/turmas`, `/turmas/{id}`, `/turmas/{id}/alunos`, `/turmas/{id}/profissionais/**`, `/me/alunos` (exato), `/me/turmas/**`, `/me/chat/**` |
| **diario** | `/turmas/{id}/alunos/{aid}/diario/**`, `/me/alunos/{aid}/diario` |
| **assiduidade** | `/turmas/{id}/assiduidade`, `/turmas/{id}/alunos/{aid}/assiduidade/{dia}`, `/alunos/{id}/assiduidade`, `/alunos/{id}/faltas/**` |
| **comunicados** | `/turmas/{id}/comunicados/**`, `/conversas/**` |
| **notificacoes** | `/me/notificacoes/**` |

Colisões a resolver, as que o teste da secção 7 tem de cobrir:
- `/me` (auth) contra `/me/alunos` (escolar), `/me/alunos/{id}/diario` (diario) e `/me/notificacoes` (notificacoes).
- `/alunos/{id}` (escolar) contra `/alunos/{id}/assiduidade` e `/alunos/{id}/faltas/**` (assiduidade).
- `/turmas/{id}/alunos` (escolar) contra `/turmas/{id}/alunos/{aid}/diario` (diario) e `.../assiduidade/{dia}` (assiduidade).

### Fora do gateway, de propósito
- **`/internal/**`**: sem rota. O gateway remove também qualquer cabeçalho `X-Internal-Key` vindo de fora.
- **`POST /registo`**: o auth devolve sempre 403 (registo público desativado), por isso não se expõe.
- **`/health` e `/ready` dos serviços**: usados só pelo gateway (health checks ativos) e pelo Docker.

### Documentação da API
`/api/docs/{servico}` e `/api/openapi/{servico}.yaml` encaminham para o `/docs` e o `/openapi.yaml` de cada serviço, sem autenticação, como hoje.

---

## 5. Autenticação no gateway

### Fase de arranque (recomendada): validar a assinatura, manter o `/me`
O gateway valida o JWT localmente (assinatura HS256, `exp`, `iss`, `aud`) e **recusa logo** o que for inválido. Os serviços continuam a chamar o `/me`.

- É o que o README descreve ("valida o token JWT e encaminha o pedido").
- Poupa chamadas ao auth e ao resto da cadeia para tráfego sem token ou com token expirado.
- **Mantém a segurança atual**: uma conta desativada, ou com mudança de palavra-passe pendente, continua a ser bloqueada pelo `/me`. Se o gateway fosse a única barreira, uma conta desativada continuaria a funcionar até 15 minutos.

Rotas públicas, sem token: só `POST /api/login` e a documentação. `POST /api/password/alterar` exige token, mas não exige que a palavra-passe já tenha sido alterada.

### Custo a aceitar
O gateway precisa de `JWT_SECRET_KEY`. Como o segredo é simétrico, **quem o tem também consegue emitir tokens**. Fica só em variável de ambiente, nunca no repositório. Em Kubernetes, vai para um Secret, como as credenciais do Atlas.

### Fora de âmbito por agora
Evitar as chamadas ao `/me` nos serviços (o gateway injetaria `X-User-Id` e `X-User-Perfil`) obrigava a mexer em todos os serviços e a garantir que só o gateway lhes chega. Só compensa com chaves assimétricas (RS256). Fica como evolução futura, sem data.

---

## 6. Outras responsabilidades do gateway

- **Limite de tentativas:** `POST /api/login` com limite apertado (por exemplo 5 por minuto por IP). Resto da API com limite largo, por utilizador.
- **Limites de corpo por rota**, alinhados com os serviços: auth e diario 16 KB, assiduidade 6 MB, comunicados 26 MB (vídeo até 25 MB). O Kestrel tem um limite global por omissão de cerca de 28,6 MB, que cobre o pior caso, mas convém fixar por rota.
- **Timeouts:** curtos por omissão. Mais longos só nas rotas de upload de vídeo e fotografia de comunicados.
- **CORS:** ativo só em desenvolvimento (por exemplo origem `http://localhost:5173`). Em produção o CloudFront serve a aplicação e `/api` na mesma origem, por isso não é preciso.
- **Cache:** o gateway não guarda nada em cache e preserva o `Cache-Control: no-store` que os serviços já enviam.
- **Erros:** quando um serviço está em baixo, o gateway devolve o mesmo formato dos serviços, `{"error": "dependency_unavailable", "message": "..."}`, com 502 ou 504.
- **Rastreio:** gera `X-Request-Id` se o cliente não enviar, passa-o aos serviços e escreve-o no log de acessos.
- **Health checks ativos** a `/health` de cada serviço. Um serviço em baixo deixa de receber pedidos.
- **Sem retries** em métodos não idempotentes (`POST`, `PATCH`, `PUT`, `DELETE`).

---

## 7. Fases

### Fase A — Esqueleto e roteamento
- Projeto `backend/gateway/` (YARP), `Dockerfile` e serviço `gateway` no `compose.yaml`, com `depends_on` dos serviços em `service_healthy`.
- Tabela de rotas da secção 4, ainda **sem autenticação**.
- **Teste da tabela de rotas:** uma lista de pares (método, caminho) e o serviço esperado, incluindo as colisões. É a rede de segurança mais importante do plano.
- Os serviços deixam de publicar portas. Para desenvolvimento fica um `compose.debug.yaml` que as volta a abrir, porque os scripts de `testes_manuais/` e os testes de integração usam `127.0.0.1:500x`.

### Fase B — Autenticação
- Validação do JWT, rotas públicas, remoção de `X-Internal-Key`.
- Testes: sem token, token expirado, token com `aud` errado, `/login` público, `/internal/...` a devolver 404.

### Fase C — Proteção e operação
- Limite de tentativas, limites de corpo e timeouts por rota, CORS em desenvolvimento, `X-Request-Id`, health checks ativos, agregação das docs.

### Fase D — Migração dos clientes
- Atualizar `testes_manuais/` para `http://127.0.0.1:8080/api/...`.
- Atualizar o README: secção de arquitetura e de arranque.
- Quando existir frontend, aponta só para `/api`.

### Em Kubernetes (k3s)
O gateway é o único serviço exposto (NodePort ou Ingress). Os restantes passam a ClusterIP. Convém correr 2 réplicas, para o gateway não ser ponto único de falha.

---

## 8. Riscos

| Risco | Mitigação |
|---|---|
| Rota encaminhada para o serviço errado | Teste da tabela de rotas na Fase A, a correr a cada alteração |
| `JWT_SECRET_KEY` replicado num segundo sítio | Só em variável de ambiente ou Secret; migrar para RS256 se o risco não for aceitável |
| Conta desativada continua a passar o gateway | O `/me` dos serviços mantém-se; só deixa de ser a única barreira |
| Gateway em baixo derruba toda a API | Health check, 2 réplicas em k3s |
| Latência de um salto extra | Esperada na ordem de milissegundos; compensada pelas chamadas ao auth evitadas em pedidos inválidos |
| Scripts de teste e documentação ficam desatualizados | Fase D, mais o `compose.debug.yaml` durante a transição |

---

## 9. Decisões para a equipa

1. **YARP (.NET)** ou Traefik/Nginx? (secção 2)
2. **Prefixo `/api`** sem nome de serviço nos URLs, como proposto? (secção 4)
3. **Limites de tentativas:** 5 por minuto no login e quanto no resto? (secção 6)
4. **Manter o `/me` nos serviços** na primeira versão, como recomendado? (secção 5)
