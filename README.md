# Trabalho-BD-II-

# 📌 Objetivo
 O simulador ilustra como o controle de concorrência pode ser feito entre várias transações que tentam acessar recursos compartilhados (no caso, X e Y) de forma segura, utilizando a política de Wait-Die, uma técnica baseada em timestamp para prevenir deadlocks.

# 🛠️ Funcionalidades
- Geração automática de timestamps para ordenar transações.
- Requisição de locks com verificação da política Wait-Die:
- Transações com timestamp mais antigo esperam.
- Transações com timestamp mais novo abortam.
- Threads simulando o comportamento de transações reais com atrasos e reinícios.
- Registro detalhado das operações no terminal, permitindo acompanhar o comportamento das transações.
