# Coleção Postman

Pedidos para todas as rotas da API, através do API Gateway (`http://localhost:8081/api`).

| Ficheiro | O que é |
|---|---|
| `EduConecta.postman_collection.json` | 67 pedidos, agrupados por serviço, com testes e variáveis |
| `EduConecta.local.postman_environment.json` | Ambiente `EduConecta - Local`: `baseUrl`, `email` e `password` |

## Como usar

1. No Postman, **Import** dos dois ficheiros e escolha o ambiente `EduConecta - Local` (canto superior direito).
2. No ambiente, preencha `email` e `password` de uma conta existente. A palavra-passe fica guardada só no seu Postman, nunca neste repositório.
3. Arranque o sistema: `docker compose up -d --build`.
4. Corra **Gateway > Estado dos serviços**. Tem de responder 200 com `"status": "ready"`. Se não, o problema é a rede ou o Atlas (ver o README principal).
5. Corra **Auth > Autenticação > Login**. O token fica guardado e todos os outros pedidos usam-no. Dura 15 minutos: se aparecer `token_expired`, volte a fazer login.

Os pedidos de criação (aluno, turma, comunicado, conversa, ...) guardam o ID devolvido, por isso os pedidos seguintes já o usam. Todas as variáveis podem ser alteradas em *Variables*, na coleção.

## O que cada pasta contém

| Pasta | Conteúdo |
|---|---|
| **Gateway** | Verificações sem login: estado, 401 sem token, 404 em rotas que não existem. Cada uma tem testes |
| **Auth** | Login, conta própria, alterar palavra-passe e administração de contas |
| **Gestão escolar** | Alunos, turmas, encarregados, profissionais e validação de conversas |
| **Assiduidade** | Marcação de faltas e justificações |
| **Diário** | Registos diários |
| **Comunicados** | Comunicados, fotografias e conversas privadas |
| **Notificações** | Listar e marcar como lida |

Cada perfil só consegue chamar as rotas que lhe cabem: criar alunos ou turmas exige uma conta de administrador, marcar faltas exige docente ou educador, e assim por diante. Um 403 vindo do serviço significa que a conta não tem esse perfil.

Os pedidos com ficheiros (justificação de falta, fotografias, vídeo) têm o campo do ficheiro vazio: escolha o ficheiro em *Body > form-data*.

## Executar a coleção sem abrir o Postman

Com o [Newman](https://github.com/postmanlabs/newman):

```bash
npm install -g newman
newman run postman/EduConecta.postman_collection.json -e postman/EduConecta.local.postman_environment.json --folder Gateway
```

A pasta **Gateway** não precisa de login. Correr a coleção toda só faz sentido com contas dos perfis certos, porque os pedidos dependem uns dos outros.

## Atualizar a coleção

A coleção foi gerada a partir dos `openapi.yaml` dos serviços. Quando uma rota é acrescentada ou alterada, o mais simples é editar o pedido no Postman e exportar a coleção para este ficheiro.
