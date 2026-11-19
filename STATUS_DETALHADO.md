# 🎓 EduConecta - Status do Projeto (19 de Novembro de 2026)

## ✅ PROJETO COMPLETAMENTE ATIVO

Todos os **9 containers** estão em execução, saudáveis e prontos para uso!

---

## 📊 Arquitetura de Microserviços

```
┌─────────────────────────────────────────────────────────────────┐
│                      🌐 API GATEWAY                             │
│                   (http://127.0.0.1:8081)                       │
│           • Autenticação JWT                                    │
│           • Limites de pedidos                                  │
│           • Encaminhamento de rotas                             │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ├─────────────────────────────────────────────┐
       │                                             │
       ▼                                             ▼
   ┌───────────┐    ┌────────────────────────────────────────┐
   │   AUTH    │    │      EVENTOS ASSÍNCRONOS (RabbitMQ)   │
   │  Service  │    │  • falta.registada                    │
   │  :8000    │    │  • falta.justificacao.submetida       │
   │           │    │  • falta.justificacao.decidida        │
   │ JWT       │    │  • comunicado.criado                  │
   │ Token     │    │  • aluno.eliminado                    │
   │ Emissão   │    └────────────────────────────────────────┘
   └───────────┘                    │
       │                            │
       ├──────────────┬─────────────┼────────────┬──────────────┐
       │              │             │            │              │
       ▼              ▼             ▼            ▼              ▼
   ┌────────┐  ┌──────────┐  ┌────────┐  ┌──────────┐  ┌──────────┐
   │ESCOLAR │  │ASSIDUIDADE│ │ DIÁRIO │  │COMUNICADOS│  │NOTIFICAÇÕES│
   │Service │  │  Service  │ │Service │  │ Service  │  │  Service  │
   │ :8000  │  │  :8000    │ │ :8000  │  │  :8000   │  │   :8000   │
   │        │  │           │ │        │  │          │  │           │
   │• Turmas│  │• Faltas   │ │• Regist│  │•Comunicad│  │•Consome   │
   │• Alunos│  │• Justif.  │ │  os    │  │  os     │  │  eventos  │
   │•Profiss│  │• Anexos   │ │  de    │  │•Conversas│  │•Notificaç│
   │•Encarg.│  │• Aprovação│ │ Creche │  │  Privad.│  │ ões       │
   └────────┘  └──────────┘  └────────┘  └──────────┘  └──────────┘
       │              │             │            │              │
       └──────────────┴─────────────┴────────────┴──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   MongoDB    │
                    │   :27017     │
                    │              │
                    │ 6 Bases de   │
                    │ dados (uma   │
                    │ por serviço) │
                    └──────────────┘
```

---

## 🚀 Status Atual de Execução

### Containers em Execução

| Container | Status | Porta | Função |
|-----------|--------|-------|--------|
| `educonecta-mongodb-1` | ✅ HEALTHY | 27017 | Base de dados |
| `educonecta-rabbitmq-1` | ✅ HEALTHY | 5672/15672 | Message broker |
| `educonecta-auth-1` | ✅ HEALTHY | 8000 | Autenticação |
| `educonecta-escolar-1` | ✅ HEALTHY | 8000 | Gestão Escolar |
| `educonecta-diario-1` | ✅ HEALTHY | 8000 | Registos Diários |
| `educonecta-comunicados-1` | ✅ HEALTHY | 8000 | Comunicados |
| `educonecta-assiduidade-1` | ✅ HEALTHY | 8000 | Assiduidade |
| `educonecta-notificacoes-1` | ✅ HEALTHY | 8000 | Notificações |
| `educonecta-gateway-1` | ✅ HEALTHY | 8081 → 8080 | API Gateway |

**Total: 9/9 containers ✅ RUNNING e HEALTHY**

---

## 🌐 Acesso às Plataformas

### API REST com Swagger

**Base URL**: `http://localhost:8081/api`

#### Endpoints Públicos (sem autenticação):
- `GET /health` - Status de saúde do gateway
- `GET /ready` - Status de prontidão de todos os serviços
- `POST /auth/login` - Autenticação
- `GET /auth/docs` - Documentação do Auth

#### Documentação Interativa
- **URL**: `http://localhost:8081/api/docs`
- **Microserviços disponíveis**:
  - `auth` - Autenticação e Contas
  - `escolar` - Gestão Escolar
  - `diario` - Registos Diários
  - `assiduidade` - Faltas e Justificações
  - `comunicados` - Comunicados e Conversas
  - `notificacoes` - Notificações (apenas consumo de eventos)

### RabbitMQ Management Panel

**URL**: `http://localhost:15672`

```
Utilizador: educonecta
Palavra-passe: educonecta_123456
```

**Funcionalidades**:
- Visualizar queues e exchanges
- Monitorar mensagens
- Ver conexões e canais
- Gerir utilizadores e permissões

### MongoDB (Acesso Direto)

**Connection String**:
```
mongodb://educonecta_admin:ba76c618022866c5f55c42ee0ac7d360612f4a08a7a8a006@127.0.0.1:27017/?authSource=admin
```

**Bases de dados**:
- `auth_db` - Autenticação e Contas
- `escolar_dc` - Gestão Escolar
- `diario_db` - Registos Diários
- `educonecta_assiduidade` - Faltas e Justificações
- `comunicados_db` - Comunicados e Conversas
- `educonecta_notificacoes` - Notificações

---

## 🔐 Configuração de Segurança

### JWT (JSON Web Tokens)
- **Algoritmo**: HS256 (HMAC SHA-256)
- **Validade**: 15 minutos
- **Secret Key**: `bacbd055a07a950880d45655c5bc87d29621d616f20b5955d66955a0a30384ac`
- **Interno**: `trocar-por-outro-segredo-com-pelo-menos-32-caracteres`

### Comunicação Intra-Serviços
- Chave de serviço interno para chamadas entre serviços
- RabbitMQ com autenticação
- Sem exposição de portas individuais (apenas via Gateway)

---

## 📋 Perfis de Utilizador do Sistema

| Perfil | Permissões | Acesso |
|--------|-----------|--------|
| **Administrador** | Total | Configuração de tudo |
| **Docente/Educador** | Parcial | Faltas, Diário, Comunicados |
| **Auxiliar Educativo** | Limitado | Apenas Diário |
| **Encarregado Educação** | Consulta | Ver info dos filhos |

---

## 🔄 Fluxo de Eventos (Message Queue)

### Exchange: `educonecta.eventos` (tipo: topic)

| Routing Key | Publicador | Consumidor | Descrição |
|------------|-----------|-----------|-----------|
| `falta.registada` | Assiduidade | Notificações | Avisa encarregados |
| `falta.justificacao.submetida` | Assiduidade | Notificações | Avisa profissionais |
| `falta.justificacao.decidida` | Assiduidade | Notificações | Avisa encarregados |
| `comunicado.criado` | Comunicados | Notificações | Avisa encarregados |
| `aluno.eliminado` | Escolar | Notificações | Auditoria |

**Padrão**: "Melhor esforço" - eventos não param o pedido HTTP se RabbitMQ falhar

---

## 🧪 Testar o Sistema

### 1. Health Check (sem autenticação)
```bash
curl http://localhost:8081/api/health
```

### 2. Status de Prontidão
```bash
curl http://localhost:8081/api/ready
```

### 3. Com Postman
Importar: `postman/EduConecta.postman_collection.json`
Usar environment: `EduConecta.local.postman_environment.json`

### 4. Scripts de Teste
```bash
cd testes_manuais
python teste_acesso.py
```

---

## 🔧 Comandos Docker

### Status dos Containers
```bash
cd C:\Users\rodri\Desktop\Universidade\MEI\Sistemas_Computacao_Cloud\EduConecta\EduConecta_projeto
docker compose -f compose.local.yaml ps
```

### Logs de um Serviço
```bash
docker compose -f compose.local.yaml logs <serviço> --tail 50
```

Exemplo:
```bash
docker compose -f compose.local.yaml logs auth --tail 50
docker compose -f compose.local.yaml logs rabbitmq --tail 20
```

### Parar Tudo
```bash
docker compose -f compose.local.yaml down
```

### Reiniciar Tudo
```bash
docker compose -f compose.local.yaml up -d
```

### Remover Containers e Volumes
```bash
docker compose -f compose.local.yaml down -v
```

### Recriar Containers
```bash
docker compose -f compose.local.yaml up -d --force-recreate
```

---

## 📁 Arquivos Importantes

| Arquivo | Descrição |
|---------|-----------|
| `compose.local.yaml` | ⭐ Docker Compose com MongoDB local (ATIVO) |
| `compose.yaml` | Docker Compose original (requer Atlas) |
| `compose.debug.yaml` | Compose com portas expostas para debug |
| `.env` | Variáveis de ambiente (credenciais, URLs) |
| `.env.smtp` | Configuração SMTP para envio de emails |
| `PROJETO_ATIVO.md` | Documentação do projeto ativo |
| `postman/` | Coleção e environment do Postman |
| `testes_manuais/` | Scripts Python de teste |
| `docs/` | Documentação técnica |

---

## 🏗️ Estrutura de Código

```
backend/
├── gateway/
│   ├── app.py              (Aplicação principal)
│   ├── rotas.py            (Definição de rotas)
│   ├── controllers/        (Lógica)
│   │   ├── gateway_controller.py
│   │   └── proxy_controller.py
│   ├── utils/              (Utilitários)
│   │   ├── tokens.py       (JWT)
│   │   ├── limite.py       (Rate limiting)
│   │   ├── respostas.py    (Formatação)
│   │   └── saude.py        (Health checks)
│   └── tests/              (Testes)
│
└── services/
    ├── auth/               (Autenticação)
    │   ├── app.py
    │   ├── db.py           (MongoDB)
    │   ├── controllers/
    │   ├── models/
    │   └── utils/
    │
    ├── escolar/            (Gestão Escolar)
    ├── assiduidade/        (Faltas)
    ├── diario/             (Registos Diários)
    ├── comunicados/        (Comunicados)
    └── notificacoes/       (Notificações)
```

---

## 🚀 Próximas Ações Sugeridas

1. **Testar API** - Aceder a `http://localhost:8081/api/docs` para explorar endpoints
2. **RabbitMQ** - Aceder a `http://localhost:15672` para visualizar eventos
3. **Executar Testes** - Rodar pytest em cada serviço
4. **Usar Postman** - Importar coleção e fazer requisições
5. **Explorar Logs** - Analisar comportamento com `docker compose logs`

---

## 📞 Informações do Projeto

**Projeto**: EduConecta - Plataforma de Comunicação Escolar
**Disciplina**: Arquiteturas e Integração de Sistemas
**Curso**: Mestrado em Engenharia Informática
**Instituição**: Instituto Politécnico do Cávado e do Ave (IPCA)
**Docente**: Bruno Lima

**Equipa**:
- Joel Oliveira (28001)
- Fábio Rodrigues (20079)
- Emma (37847)

---

## 📝 Notas Importantes

✅ **Sistema Totalmente Funcional**
- Todos os 9 containers estão ativos
- Todas as dependências funcionam corretamente
- API Gateway pronto para receber requisições
- RabbitMQ pronto para processar eventos
- MongoDB pronto para armazenar dados

🔄 **Comunicação entre Serviços**
- Síncrona: REST APIs
- Assíncrona: RabbitMQ (eventos)
- Descoberta: DNS interno do Docker

🛡️ **Segurança**
- Autenticação JWT obrigatória (exceto em endpoints públicos)
- Validação de tokens no Gateway e nos serviços
- Isolamento de dados (database per service)
- RabbitMQ com credenciais

📊 **Escalabilidade**
- Arquitetura preparada para Kubernetes
- Volumes persistentes para dados
- Healthchecks configurados
- Pronto para ambiente cloud (AWS)

---

**Última atualização**: 19 de Novembro de 2026 às 19:40 UTC
**Status**: ✅ TODOS OS SERVIÇOS OPERACIONAIS
