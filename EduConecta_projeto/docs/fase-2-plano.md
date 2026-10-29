# Fase 2 — RabbitMQ e notificações

Documento para aprovação antes de começar a implementar (mesmo formato da Fase 1).

---

## 1. Infraestrutura — RabbitMQ no `compose.yaml`

Novo serviço no `compose.yaml`, imagem oficial com plugin de gestão (dá um painel web para ver filas/mensagens em `http://localhost:15672`, útil para a demonstração do projeto):

```yaml
rabbitmq:
  image: rabbitmq:3.13-management
  ports:
    - "127.0.0.1:5672:5672"     # protocolo AMQP — os serviços ligam aqui
    - "127.0.0.1:15672:15672"   # painel web
  environment:
    RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER:?Falta RABBITMQ_USER no .env}
    RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASS:?Falta RABBITMQ_PASS no .env}
  healthcheck:
    test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 15s
```

Cada serviço que publica/consome passa a ter `depends_on: rabbitmq: condition: service_healthy` e uma variável `RABBITMQ_URL` (ex: `amqp://user:pass@rabbitmq:5672/`).

### Desenho de mensagens
- Um único **exchange topic**: `educonecta.eventos`.
- Cada serviço publica com uma routing key própria (`aluno.eliminado`, `comunicado.criado`, `falta.justificacao.submetida`, `falta.justificacao.decidida`...).
- O `notificacoes` (novo serviço, secção 3) liga uma fila a todas as routing keys relevantes (`#` ou uma lista) — é o único consumidor para já.

### Bibliotecas
- `pika` (síncrono) nos 4 serviços Flask — publicar é só "enviar e seguir", não precisa de assincronismo.
- `aio-pika` no `auth`, coerente com o resto do serviço já ser Quart/async — mas o `auth` não tem nenhum evento óbvio para publicar agora, por isso só entra se for preciso.

---

## 2. Eventos propostos nesta fase

| Evento (routing key) | Publicado por | Quando | Consumido por |
|---|---|---|---|
| `aluno.eliminado` | `escolar` | `DELETE /alunos/{id}` | `notificacoes` (nada a notificar a ninguém, mas grava um registo de auditoria) — **e também resolve o limitação conhecida da Fase 1**: o `diario`/`assiduidade` passam a ter um consumidor próprio que marca os registos desse aluno como `aluno_eliminado: true` em vez de ficarem órfãos silenciosos |
| `comunicado.criado` | `comunicados` | `POST /comunicados` | `notificacoes` → cria uma notificação para cada encarregado da turma visada |
| `falta.justificacao.submetida` | `assiduidade` | `POST .../justificacao` | `notificacoes` → notifica os profissionais da turma (há uma justificação pendente) |
| `falta.justificacao.decidida` | `assiduidade` | aprovar/rejeitar | `notificacoes` → notifica o encarregado que submeteu |

Isto cobre o requisito de "RabbitMQ obrigatório" com casos de uso reais, sem inventar funcionalidade fora do que já existe. Fica de fora desta fase (posso alargar depois se fizer sentido): notificação de novo registo no diário, chat em tempo real via RabbitMQ (o chat já funciona por polling HTTP, não mexe).

---

## 3. Novo microsserviço `notificacoes`

Seguindo a mesma estrutura MVC dos outros 4 serviços Flask síncronos (`app.py`, `db.py`, `models/`, `controllers/`, `utils/`, `tests/`), porta `:5006`, base de dados própria `educonecta_notificacoes`.

### Modelo de dados (coleção `notificacoes`)
```
{
  _id,
  destinatario_utilizador_id,   # quem deve ver a notificação
  tipo: "comunicado" | "justificacao_pendente" | "justificacao_decidida",
  titulo: str,
  mensagem: str,
  referencia: { turma_id, aluno_id, comunicado_id, ... },  # conforme o tipo
  lida: bool,
  criada_em: datetime,
}
```

### Consumidor
Um processo/thread dentro do próprio `notificacoes` que arranca junto com a app, liga-se à fila do RabbitMQ e, por cada mensagem recebida, grava um documento. Para saber **quem** é o destinatário (ex: "os encarregados desta turma"), o consumidor chama o `escolar` (`GET /turmas/{id}/alunos` ou equivalente) da mesma forma que os outros serviços já fazem — reaproveita o padrão existente, não inventa nada novo.

### Endpoints HTTP (para o próprio utilizador consultar as notificações)
| Rota | Perfil | O que faz |
|---|---|---|
| `GET /me/notificacoes` | qualquer conta autenticada | Lista as notificações do utilizador autenticado (mais recentes primeiro, paginado como os outros serviços) |
| `PATCH /me/notificacoes/{id}/lida` | dono da notificação | Marca como lida |

### Testes
Mesma abordagem já usada nos outros serviços: pytest + mocks (a lógica do consumidor é testável isolando a função que processa uma mensagem, sem precisar de um RabbitMQ real a correr).

---

## Fora de âmbito para a Fase 2 (fica assinalado)
- Envio de **email** nas notificações (só ficam visíveis via `GET /me/notificacoes`) — o `auth` já envia email para credenciais, mas ligar isso às notificações é mais código e não está pedido explicitamente; posso adicionar depois se fizer sentido.
- Retry/dead-letter queue — para um projeto académico, se uma mensagem falhar a app simplesmente perde-a; não vale a pena a complexidade de DLQ agora.
- Deploy cloud / Kubernetes do RabbitMQ (RNF09/10) — continua adiado para o fim, como já combinado.

---

## Resumo do que preciso que confirmes antes de começar

1. Aceitas a lista de 4 eventos da secção 2, ou falta algum caso de uso que sabes que está no enunciado?
2. Aceitas criar um 6º microsserviço `notificacoes` (porta 5006), em vez de meter a lógica de consumo dentro de um serviço já existente?
3. Fico só com notificação "in-app" (via `GET /me/notificacoes`) nesta fase, sem email — aceitas adiar o email para depois?
