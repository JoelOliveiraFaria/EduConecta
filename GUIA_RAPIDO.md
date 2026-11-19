# ⚡ Guia Rápido - EduConecta

## 🎯 Começar Rapidamente

### 1️⃣ Verificar Status
```bash
cd C:\Users\rodri\Desktop\Universidade\MEI\Sistemas_Computacao_Cloud\EduConecta\EduConecta_projeto
docker compose -f compose.local.yaml ps
```

**Esperado**: Todos os containers com status `Up` e `(healthy)`

### 2️⃣ Aceder à API
```
🌐 http://localhost:8081/api/docs
```
👉 Escolha um microserviço e explore os endpoints

### 3️⃣ Monitorar RabbitMQ
```
🐰 http://localhost:15672
Utilizador: educonecta
Palavra-passe: educonecta_123456
```

### 4️⃣ Ver Logs de um Serviço
```bash
docker compose -f compose.local.yaml logs auth --tail 50
```

---

## 🔥 Problemas Comuns

### "Connection refused" ao aceder à API
```bash
# Verificar se os containers estão a correr
docker compose -f compose.local.yaml ps

# Se não estão, iniciar
docker compose -f compose.local.yaml up -d
```

### Um serviço está em "Restarting"
```bash
# Ver o erro
docker compose -f compose.local.yaml logs <serviço>

# Reiniciar tudo
docker compose -f compose.local.yaml down
docker compose -f compose.local.yaml up -d --build
```

### MongoDB não consegue conectar
```bash
# Verificar container MongoDB
docker compose -f compose.local.yaml logs mongodb

# Resetar tudo (apaga dados!)
docker compose -f compose.local.yaml down -v
docker compose -f compose.local.yaml up -d
```

---

## 📚 Documentação por Serviço

### Auth (Autenticação)
```
GET  /health                     - Status
POST /login                      - Fazer login
GET  /me                         - Dados do utilizador
POST /refresh                    - Renovar token
GET  /docs                       - Documentação
```

### Escolar (Gestão)
```
GET  /health                     - Status
GET  /turmas                     - Listar turmas
GET  /alunos                     - Listar alunos
GET  /encarregados               - Listar encarregados
GET  /profissionais              - Listar profissionais
```

### Assiduidade (Faltas)
```
GET  /ready                      - Status
POST /faltas                     - Registar falta
GET  /faltas/{id}                - Ver falta
POST /faltas/{id}/justificacao   - Submeter justificação
PUT  /justificacoes/{id}         - Aprovar/rejeitar
```

### Diário (Registos)
```
GET  /health                     - Status
GET  /registos                   - Listar registos
POST /registos                   - Criar registo
GET  /registos/{id}              - Ver registo detalhado
```

### Comunicados
```
GET  /ready                      - Status
GET  /comunicados                - Listar comunicados
POST /comunicados                - Criar comunicado
GET  /conversas                  - Listar conversas
POST /conversas/{id}/mensagens   - Enviar mensagem
```

### Notificações
```
GET  /ready                      - Status
GET  /notificacoes               - Listar notificações
PUT  /notificacoes/{id}/lida     - Marcar como lida
```

---

## 🔐 Autenticação JWT

### 1. Fazer Login
```bash
POST http://localhost:8081/api/auth/login
Content-Type: application/json

{
  "email": "utilizador@exemplo.com",
  "palavra_passe": "senha123"
}
```

### 2. Usar Token nos Pedidos
```bash
GET http://localhost:8081/api/escolar/turmas
Authorization: Bearer eyJhbGc...
```

### 3. Token Expira em
```
15 minutos
```

Depois usar `/refresh` para renovar!

---

## 🐳 Comandos Docker Úteis

```bash
# Ver todos os containers
docker compose -f compose.local.yaml ps

# Ver logs (últimas 50 linhas)
docker compose -f compose.local.yaml logs <serviço> --tail 50

# Ver logs em tempo real
docker compose -f compose.local.yaml logs -f <serviço>

# Parar um serviço
docker compose -f compose.local.yaml stop <serviço>

# Iniciar um serviço parado
docker compose -f compose.local.yaml start <serviço>

# Reiniciar um serviço
docker compose -f compose.local.yaml restart <serviço>

# Parar TUDO
docker compose -f compose.local.yaml down

# Iniciar TUDO
docker compose -f compose.local.yaml up -d

# Remover tudo (incluindo volumes/dados!)
docker compose -f compose.local.yaml down -v
```

---

## 💾 Dados e Configuração

### Localização dos Dados
```
Volume: mongo_data/
Local: C:\Users\rodri\Desktop\Universidade\MEI\Sistemas_Computacao_Cloud\EduConecta\EduConecta_projeto\mongo_data
```

### Variáveis de Ambiente
```
Arquivo: .env
Usado por: Todos os containers
Contém: Credenciais, URLs, Segredos
```

### SMTP (Envio de Emails)
```
Arquivo: .env.smtp
Usado por: Auth Service
Para definir: SMTP_USERNAME e SMTP_PASSWORD
```

---

## 🧪 Testar Microserviços

### Com cURL (bash/PowerShell)
```bash
curl http://localhost:8081/api/health
curl http://localhost:8081/api/ready
```

### Com Postman
1. Abrir `postman/EduConecta.postman_collection.json`
2. Usar environment `EduConecta.local.postman_environment.json`
3. Executar requisições

### Com Python (scripts)
```bash
cd testes_manuais
python teste_acesso.py
```

---

## 🔧 Build e Atualizar

### Recriar Imagens
```bash
docker compose -f compose.local.yaml up -d --build
```

### Atualizar um Serviço
```bash
# Modificar código em backend/services/<serviço>/
# Depois:
docker compose -f compose.local.yaml up -d --build <serviço>
```

### Verificar Logs de Build
```bash
docker compose -f compose.local.yaml logs <serviço>
```

---

## 📊 Status dos Serviços

| Serviço | Host | Porta Interna | Função |
|---------|------|---|---------|
| Gateway | localhost | 8080 (8081 externamente) | Entrada da API |
| Auth | auth | 8000 | Autenticação |
| Escolar | escolar | 8000 | Gestão |
| Assiduidade | assiduidade | 8000 | Faltas |
| Diário | diario | 8000 | Registos |
| Comunicados | comunicados | 8000 | Comunicados |
| Notificações | notificacoes | 8000 | Notificações |
| MongoDB | mongodb | 27017 | Base de dados |
| RabbitMQ | rabbitmq | 5672 (15672 UI) | Message broker |

---

## 📞 Contactos

**Problemas com o Projeto?**
1. Verificar logs: `docker compose logs <serviço>`
2. Consultar `STATUS_DETALHADO.md`
3. Revisar `README.md` no repositório

**Documentação**
- API Swagger: `http://localhost:8081/api/docs`
- README: `EduConecta/README.md`
- Arquitetura: `EduConecta_projeto/EduConecta_Arquitetura_Handoff.pdf`

---

✅ **Projeto Ready!** Comece a explorar a API em `http://localhost:8081/api/docs`
