# 🎓 EduConecta - Projeto Ativo

## Status: ✅ TODOS OS CONTAINERS EM EXECUÇÃO

Data de início: 19 de Novembro de 2026

---

## 📋 Resumo da Arquitetura

O projeto EduConecta é uma **plataforma de comunicação entre escolas e famílias** com arquitetura baseada em **microserviços**.

### Componentes em Execução:

#### 🔌 Infraestrutura
- **MongoDB** (127.0.0.1:27017) - Base de dados para todos os serviços
- **RabbitMQ** (127.0.0.1:5672 | Painel: 127.0.0.1:15672) - Message broker para eventos assíncronos

#### 🛡️ Gateway & Autenticação
- **API Gateway** (127.0.0.1:8081) - Ponto único de entrada para toda a API
- **Auth Service** - Autenticação, autorização e JWT

#### 📚 Microserviços
1. **Escolar** - Gestão de turmas, alunos, profissionais e encarregados
2. **Assiduidade** - Registo e justificação de faltas
3. **Diário** - Registos diários de creche (alimentação, sono, higiene, atividades)
4. **Comunicados** - Comunicados e conversas privadas entre profissionais e encarregados
5. **Notificações** - Consumo de eventos e notificações para utilizadores

---

## 🌐 Acesso aos Serviços

### API
- **Base URL**: `http://localhost:8081/api`
- **Docs**: `http://localhost:8081/api/docs` (Swagger UI)
- **Health Check**: `http://localhost:8081/api/health`
- **Ready Status**: `http://localhost:8081/api/ready`

### RabbitMQ
- **Management Panel**: `http://localhost:15672`
- **Utilizador**: `educonecta`
- **Palavra-passe**: `educonecta_123456`

### MongoDB
- **Connection String**: `mongodb://educonecta_admin:ba76c618022866c5f55c42ee0ac7d360612f4a08a7a8a006@mongodb:27017/?authSource=admin`
- **Host**: `127.0.0.1:27017`

---

## 📊 Status dos Serviços

Todos os serviços estão **RUNNING** e **HEALTHY**:

```
✅ educonecta-mongodb-1        (mongo:7)
✅ educonecta-rabbitmq-1       (rabbitmq:3.13-management)
✅ educonecta-auth-1           (Auth Service)
✅ educonecta-escolar-1        (Escolar Service)
✅ educonecta-diario-1         (Diário Service)
✅ educonecta-comunicados-1    (Comunicados Service)
✅ educonecta-assiduidade-1    (Assiduidade Service)
✅ educonecta-notificacoes-1   (Notificações Service)
✅ educonecta-gateway-1        (API Gateway)
```

---

## 🔧 Comandos Úteis

### Ver Status dos Containers
```bash
cd C:\Users\rodri\Desktop\Universidade\MEI\Sistemas_Computacao_Cloud\EduConecta\EduConecta_projeto
docker compose -f compose.local.yaml ps
```

### Ver Logs de um Serviço
```bash
docker compose -f compose.local.yaml logs <serviço> --tail 50
```

### Parar Todos os Containers
```bash
docker compose -f compose.local.yaml down
```

### Iniciar Containers Novamente
```bash
docker compose -f compose.local.yaml up -d
```

### Executar Testes de um Serviço
```bash
cd backend/services/<serviço>
pip install -r requirements-dev.txt
pytest
```

---

## 🔄 Fluxo de Eventos (RabbitMQ)

O sistema publica eventos para o exchange `educonecta.eventos` (tipo topic):

| Evento | Publicador | Consumidor |
|--------|-----------|-----------|
| `falta.registada` | Assiduidade | Notificações |
| `falta.justificacao.submetida` | Assiduidade | Notificações |
| `falta.justificacao.decidida` | Assiduidade | Notificações |
| `comunicado.criado` | Comunicados | Notificações |
| `aluno.eliminado` | Escolar | Notificações |

---

## 📁 Estrutura do Projeto

```
EduConecta_projeto/
├── compose.yaml              # Docker Compose original (requer Atlas)
├── compose.local.yaml        # Docker Compose com MongoDB local ⭐ ATIVO
├── compose.debug.yaml        # Compose com portas expostas para debug
├── .env                       # Variáveis de ambiente
├── backend/
│   ├── gateway/              # API Gateway
│   └── services/
│       ├── auth/             # Autenticação
│       ├── escolar/          # Gestão Escolar
│       ├── assiduidade/      # Faltas e Justificações
│       ├── diario/           # Registos Diários
│       ├── comunicados/      # Comunicados e Conversas
│       └── notificacoes/     # Notificações
├── postman/                  # Coleção Postman para testes
└── docs/                     # Documentação
```

---

## 🧪 Testar a API

### Com cURL (fora do container):
```bash
curl http://localhost:8081/api/health
curl http://localhost:8081/api/ready
```

### Com Postman:
Importar a coleção em `postman/EduConecta.postman_collection.json` e usar o environment `EduConecta.local.postman_environment.json`

### Com Python (scripts em `testes_manuais/`):
```bash
cd testes_manuais
python teste_acesso.py
```

---

## 🔐 Autenticação JWT

- **Algoritmo**: HS256
- **Validade**: 15 minutos
- **Secret Key**: Definido em `.env` como `JWT_SECRET_KEY`

---

## 📝 Notas Importantes

1. **MongoDB Local**: O sistema está configurado com MongoDB em container local. Nenhum acesso à internet é necessário.
2. **Volumes Persistentes**: Os dados do MongoDB são armazenados em `mongo_data/` (volume Docker).
3. **Redes Internas**: Os microserviços comunicam através de uma rede Docker interna. Apenas o Gateway expõe uma porta (8081).
4. **Healthchecks**: Todos os containers têm healthchecks configurados para garantir disponibilidade.

---

## 📞 Perfis de Utilizador no Sistema

| Perfil | Acesso |
|--------|--------|
| **Administrador** | Configuração da instituição |
| **Docente/Educador** | Registo de faltas, diário, comunicados |
| **Auxiliar de ação educativa** | Acompanhamento diário |
| **Encarregado de educação** | Consulta de informação, justificações, comunicados |

---

## 🚀 Próximos Passos

1. Testar endpoints da API através do Swagger em `http://localhost:8081/api/docs`
2. Explorar o painel do RabbitMQ em `http://localhost:15672`
3. Executar testes automatizados em cada serviço
4. Usar scripts de teste manual em `testes_manuais/`

---

**Projeto em desenvolvimento** para a unidade curricular **Arquiteturas e Integração de Sistemas** (Mestrado em Engenharia Informática, IPCA).
