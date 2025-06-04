# -*- coding: utf-8 -*-
import threading
import time
import random
import sys

#===============================================================================
# Classe GerenciadorRecursos
# Objetivo: Controlar o acesso aos recursos compartilhados (X e Y) e 
#           implementar a lógica de prevenção de deadlock (Wait-Die).
#===============================================================================

class GerenciadorRecursos:
    """Gerencia o acesso concorrente aos recursos compartilhados X e Y,
       implementando a prevenção de deadlock com a técnica Wait-Die.
    """
    def __init__(self):
        """Inicializa o gerenciador.
        - Define a estrutura para rastrear o estado de cada recurso (quem o detém, timestamp, fila de espera).
        - Cria um Lock (mutex) para garantir que as operações no gerenciador sejam atômicas (thread-safe).
        - Inicializa o contador de timestamps.
        """
        self.recursos = {
            'X': {'lock_holder_id': None, 'lock_holder_timestamp': -1, 'waiting_transactions': []},
            'Y': {'lock_holder_id': None, 'lock_holder_timestamp': -1, 'waiting_transactions': []}
        }
        self.lock = threading.Lock()
        self.next_timestamp = 0

    def get_timestamp(self) -> int:
        """Gera e retorna um novo timestamp único e sequencial para uma transação.
        Utiliza o lock global para garantir que a geração seja segura em ambiente com múltiplas threads.
        """
        with self.lock:
            timestamp = self.next_timestamp
            self.next_timestamp += 1
            return timestamp

    def request_lock(self, transaction_id: int, timestamp: int, item_id: str) -> str:
        """Processa uma solicitação de bloqueio (lock) para um recurso ('X' ou 'Y').
        Implementa a lógica Wait-Die:
        - Se o recurso está livre, concede o lock.
        - Se a própria transação já tem o lock, concede novamente (idempotente).
        - Se o recurso está ocupado por outra transação (Tj):
            - Compara o timestamp da requisitante (Ti) com o da detentora (Tj).
            - Se Ti é mais antiga (timestamp < Tj.timestamp): Ti espera ('wait').
            - Se Ti é mais nova ou igual (timestamp >= Tj.timestamp): Ti aborta ('abort').
        Retorna o status da solicitação: 'granted', 'wait', ou 'abort'.
        """
        with self.lock: # Garante que a verificação e atualização do estado do recurso sejam atômicas
            recurso = self.recursos[item_id]
            holder_id = recurso['lock_holder_id']
            holder_timestamp = recurso['lock_holder_timestamp']

            if holder_id is None:
                recurso['lock_holder_id'] = transaction_id
                recurso['lock_holder_timestamp'] = timestamp
                return 'granted'

            if holder_id == transaction_id:
                return 'granted'

            if timestamp < holder_timestamp:
                if not any(t[0] == transaction_id for t in recurso['waiting_transactions']):
                     recurso['waiting_transactions'].append((transaction_id, timestamp))
                     recurso['waiting_transactions'].sort(key=lambda x: x[1]) # Mantém a fila ordenada
                return 'wait'
            else:
                return 'abort'

    def release_lock(self, transaction_id: int, item_id: str) -> bool:
        """Libera o bloqueio de um recurso ('X' ou 'Y').
        Verifica se a transação que está tentando liberar é realmente a que detém o lock.
        Retorna True se o lock foi liberado, False caso contrário.
        """
        with self.lock: # Garante atomicidade
            recurso = self.recursos[item_id]
            if recurso['lock_holder_id'] == transaction_id:
                recurso['lock_holder_id'] = None
                recurso['lock_holder_timestamp'] = -1
                # Não remove da fila de espera aqui, as transações em espera tentarão novamente
                return True
            else:
                # Tentativa de liberar um lock não detido (pode ocorrer em cenários de erro ou aborto)
                return False

    def remove_from_wait_queues(self, transaction_id: int):
        """Remove uma transação específica de todas as filas de espera.
        Isso é chamado quando uma transação é abortada (pela lógica Wait-Die)
        para garantir que ela não fique esperando desnecessariamente.
        """
        with self.lock: # Garante atomicidade
            for item_id in self.recursos:
                recurso = self.recursos[item_id]
                # Cria uma nova lista sem a transação abortada
                recurso['waiting_transactions'] = [
                    t for t in recurso['waiting_transactions'] if t[0] != transaction_id
                ]

#===============================================================================
# Classe Transacao
# Objetivo: Representar uma transação individual que executa uma sequência 
#           de operações (locks, unlocks, esperas) sobre os recursos X e Y.
#           Cada transação roda em sua própria thread.
#===============================================================================

class Transacao(threading.Thread):
    """Representa uma transação concorrente que acessa os recursos X e Y."""

    def __init__(self, t_id: int, gerenciador_recursos: GerenciadorRecursos, max_wait_time: float = 0.5):
        """Inicializa uma nova thread de transação.
        Args:
            t_id: Identificador único da transação.
            gerenciador_recursos: A instância compartilhada do GerenciadorRecursos.
            max_wait_time: O tempo máximo para as pausas aleatórias (simula processamento).
        """
        super().__init__(name=f"Transacao-{t_id}")
        self.t_id = t_id
        self.gerenciador_recursos = gerenciador_recursos
        self.max_wait_time = max_wait_time
        self.timestamp = -1 # Timestamp será atribuído no início da execução
        self.aborted = threading.Event() # Evento para sinalizar se a transação foi abortada
        self.locks_held = set() # Conjunto para rastrear quais locks ('X', 'Y') a transação detém

    def run(self):
        """Define o comportamento da thread da transação.
        Este método é chamado automaticamente quando a thread é iniciada (`.start()`).
        Ele contém o loop principal que executa a sequência de operações:
        random_wait -> lock(X) -> random_wait -> lock(Y) -> random_wait -> unlock(X) -> random_wait -> unlock(Y) -> random_wait -> commit.
        Inclui lógica para reiniciar a sequência caso a transação seja abortada (pelo Wait-Die).
        """
        # Obtém o timestamp único no início da execução
        self.timestamp = self.gerenciador_recursos.get_timestamp()
        print(f"T{self.t_id} (TS={self.timestamp}): Iniciando execução.")

        # Loop principal para permitir o reinício após aborto
        while True:
            self.aborted.clear() # Reseta o status de aborto no início de cada tentativa
            self.locks_held.clear() # Garante que não há locks detidos no início da tentativa

            try:
                # 1. randon(t): Simula um tempo de processamento aleatório
                self.random_wait()
                if self.aborted.is_set(): continue # Verifica se foi abortada durante a espera

                # 2. lock(X): Tenta adquirir o lock no recurso X
                if not self.acquire("X"):
                    # Se acquire retornar False, a transação foi abortada
                    self.release_all_held_locks() # Libera locks que possa ter (nenhum aqui)
                    time.sleep(random.uniform(0.1, 0.3)) # Pausa antes de reiniciar
                    print(f"T{self.t_id} (TS={self.timestamp}): Reiniciando após aborto ao tentar pegar X.")
                    continue # Reinicia o loop while

                # 3. randon(t): Simula processamento
                self.random_wait()
                if self.aborted.is_set(): # Abortada durante a espera?
                   self.release_all_held_locks() # Libera X
                   time.sleep(random.uniform(0.1, 0.3))
                   print(f"T{self.t_id} (TS={self.timestamp}): Reiniciando após aborto durante espera (tinha X).")
                   continue

                # 4. lock(Y): Tenta adquirir o lock no recurso Y
                if not self.acquire("Y"):
                    # Abortada ao tentar pegar Y
                    self.release_all_held_locks() # Libera X
                    time.sleep(random.uniform(0.1, 0.3))
                    print(f"T{self.t_id} (TS={self.timestamp}): Reiniciando após aborto ao tentar pegar Y (tinha X).")
                    continue

                # 5. randon(t): Simula processamento
                self.random_wait()
                if self.aborted.is_set(): # Abortada durante a espera?
                    self.release_all_held_locks() # Libera X e Y
                    time.sleep(random.uniform(0.1, 0.3))
                    print(f"T{self.t_id} (TS={self.timestamp}): Reiniciando após aborto durante espera (tinha X, Y).")
                    continue

                # 6. unlock(X): Libera o lock do recurso X
                self.release("X")

                # 7. randon(t): Simula processamento
                self.random_wait()
                if self.aborted.is_set(): # Abortada durante a espera?
                    self.release_all_held_locks() # Libera Y
                    time.sleep(random.uniform(0.1, 0.3))
                    print(f"T{self.t_id} (TS={self.timestamp}): Reiniciando após aborto durante espera (tinha Y).")
                    continue

                # 8. unlock(Y): Libera o lock do recurso Y
                self.release("Y")

                # 9. randon(t): Simula processamento final
                self.random_wait()

                # 10. commit(t): Transação concluída com sucesso
                print(f"T{self.t_id} (TS={self.timestamp}): Commitado com sucesso!")
                break # Sai do loop while, pois a transação terminou

            except Exception as e:
                # Tratamento genérico de erro, caso algo inesperado ocorra
                print(f"T{self.t_id} (TS={self.timestamp}): Erro inesperado: {e}. Abortando e reiniciando.")
                self.aborted.set()
                self.release_all_held_locks() # Libera quaisquer locks detidos
                time.sleep(random.uniform(0.2, 0.5)) # Pausa um pouco maior
                continue # Tenta reiniciar

        # Mensagem final quando a thread termina sua execução (após o break ou erro fatal)
        print(f"T{self.t_id} (TS={self.timestamp}): Finalizada.")

    def acquire(self, item_id: str) -> bool:
        """Tenta adquirir o lock para um recurso específico ('X' ou 'Y').
        Este método encapsula a chamada ao gerenciador e trata os possíveis retornos ('granted', 'wait', 'abort').
        - Se 'granted', marca o lock como detido e retorna True.
        - Se 'wait', entra em loop de espera (com verificação de aborto) e tenta novamente.
        - Se 'abort', marca a transação como abortada, remove-se das filas de espera e retorna False.
        Retorna True se o lock foi adquirido, False se a transação foi abortada.
        """
        while True:
            # Verifica se a transação já foi marcada como abortada antes de tentar
            if self.aborted.is_set():
                return False

            print(f"T{self.t_id} (TS={self.timestamp}): Tentando adquirir lock em {item_id}...")
            # Solicita o lock ao gerenciador
            status = self.gerenciador_recursos.request_lock(self.t_id, self.timestamp, item_id)

            if status == 'granted':
                print(f"T{self.t_id} (TS={self.timestamp}): Adquiriu lock em {item_id}.")
                self.locks_held.add(item_id) # Adiciona o item ao conjunto de locks detidos
                return True # Sucesso
            elif status == 'wait':
                # Transação precisa esperar
                holder_info = self.gerenciador_recursos.recursos[item_id]
                print(f"T{self.t_id} (TS={self.timestamp}): Esperando por lock em {item_id} (detido por T{holder_info['lock_holder_id']} TS={holder_info['lock_holder_timestamp']})...")
                # Loop de espera ativa (polling) com verificação de aborto
                wait_start = time.time()
                while time.time() - wait_start < 2.0: # Espera no máximo 2 segundos antes de tentar de novo
                    if self.aborted.is_set(): # Verifica se foi abortada enquanto esperava
                        return False
                    time.sleep(random.uniform(0.1, 0.3)) # Pausa curta entre verificações
                # Após a espera, o loop while externo tentará adquirir novamente
            elif status == 'abort':
                # Transação foi abortada pela lógica Wait-Die
                holder_info = self.gerenciador_recursos.recursos[item_id]
                print(f"T{self.t_id} (TS={self.timestamp}): ABORTADA (Wait-Die) ao tentar adquirir {item_id} (detido por T{holder_info['lock_holder_id']} TS={holder_info['lock_holder_timestamp']}).")
                self.aborted.set() # Sinaliza que esta transação foi abortada
                self.gerenciador_recursos.remove_from_wait_queues(self.t_id) # Remove das filas de espera
                return False # Falha (aborto)
            else:
                 # Status inesperado retornado pelo gerenciador (erro)
                 print(f"T{self.t_id} (TS={self.timestamp}): Recebeu status inesperado '{status}' do gerenciador para {item_id}. Abortando.")
                 self.aborted.set()
                 self.gerenciador_recursos.remove_from_wait_queues(self.t_id)
                 return False

    def release(self, item_id: str):
        """Libera o lock de um recurso específico ('X' ou 'Y').
        Chama o gerenciador para liberar o lock e atualiza o conjunto de locks detidos.
        """
        # Verifica se realmente detém o lock antes de tentar liberar
        if item_id in self.locks_held:
            print(f"T{self.t_id} (TS={self.timestamp}): Liberando lock em {item_id}...")
            released = self.gerenciador_recursos.release_lock(self.t_id, item_id)
            if released:
                self.locks_held.remove(item_id) # Remove do conjunto de locks detidos
                print(f"T{self.t_id} (TS={self.timestamp}): Lock em {item_id} liberado.")
            else:
                # Log de erro: tentou liberar um lock que o gerenciador disse não ser dela
                print(f"T{self.t_id} (TS={self.timestamp}): ERRO ao liberar lock em {item_id} que constava como detido localmente!")
        # else: # Caso tente liberar algo que não está no set local (pode acontecer se abortada)
            # print(f"T{self.t_id} (TS={self.timestamp}): Aviso - Tentativa de liberar {item_id} não detido localmente.")

    def release_all_held_locks(self):
        """Libera todos os locks que a transação atualmente detém.
        Útil quando a transação é abortada ou termina inesperadamente.
        """
        # Cria uma cópia do set para poder iterar e modificar o original sem problemas
        locks_to_release = list(self.locks_held)
        if locks_to_release:
            print(f"T{self.t_id} (TS={self.timestamp}): Liberando todos os locks detidos: {locks_to_release}")
            for item_id in locks_to_release:
                self.release(item_id)

    def random_wait(self):
        """Simula um tempo de processamento esperando por um período aleatório.
        Verifica periodicamente se a transação foi abortada durante a espera.
        """
        wait_time = random.uniform(0.1, self.max_wait_time)
        # print(f"T{self.t_id} (TS={self.timestamp}): Esperando por {wait_time:.3f} segundos...")
        wait_start = time.time()
        while time.time() - wait_start < wait_time:
             if self.aborted.is_set(): # Interrompe a espera se for abortada
                 # print(f"T{self.t_id} (TS={self.timestamp}): Espera interrompida por aborto.")
                 break
             time.sleep(0.05) # Pequena pausa para não consumir CPU excessivamente

#===============================================================================
# Função Principal e Execução do Script
# Objetivo: Orquestrar a simulação: configurar parâmetros, criar o 
#           gerenciador, criar e iniciar as threads de transação, e 
#           aguardar a finalização.
#===============================================================================

# --- Configuração Padrão --- (Valores default se não passados por linha de comando)
NUM_TRANSACOES_PADRAO = 3
MAX_WAIT_TIME_TRANSACAO_PADRAO = 0.8 # Segundos
# -------------------------

def main(num_transacoes, max_wait_time):
    """Função principal que executa a simulação.
    1. Imprime informações iniciais.
    2. Cria a instância única do GerenciadorRecursos.
    3. Cria a lista de threads (instâncias da classe Transacao).
    4. Inicia todas as threads.
    5. Aguarda que todas as threads terminem (`.join()`).
    6. Imprime informações de conclusão.
    """
    print("--- Iniciando Simulação de Transações Concorrentes com Wait-Die ---")
    print(f"Número de Transações: {num_transacoes}")
    print(f"Recursos Compartilhados: X, Y")
    print("Técnica de Prevenção de Deadlock: Wait-Die")
    print("-----------------------------------------------------------------")

    # 1. Cria o gerenciador compartilhado
    gerenciador = GerenciadorRecursos()

    # 2. Cria as threads das transações
    threads = []
    for i in range(1, num_transacoes + 1):
        transacao_thread = Transacao(t_id=i,
                                     gerenciador_recursos=gerenciador,
                                     max_wait_time=max_wait_time)
        threads.append(transacao_thread)

    # 3. Inicia as threads (a execução começa no método run de cada Transacao)
    print("\n--- Iniciando Threads ---")
    start_time = time.time()
    for thread in threads:
        thread.start()

    # 4. Aguarda a finalização de todas as threads
    # O script principal fica bloqueado aqui até que todas as transações terminem
    print("\n--- Aguardando Finalização das Threads ---")
    for thread in threads:
        thread.join()

    # 5. Imprime o tempo total da simulação
    end_time = time.time()
    print("-----------------------------------------------------------------")
    print(f"--- Simulação Concluída em {end_time - start_time:.2f} segundos ---")

# Ponto de entrada do script: Este bloco só é executado quando o arquivo é rodado diretamente.
if __name__ == "__main__":
    # Define os valores a serem usados na simulação (padrão ou da linha de comando)
    num_a_executar = NUM_TRANSACOES_PADRAO
    wait_a_usar = MAX_WAIT_TIME_TRANSACAO_PADRAO

    # Verifica se um argumento foi passado na linha de comando (para o número de transações)
    if len(sys.argv) > 1:
        try:
            num_arg = int(sys.argv[1])
            if num_arg > 0:
                num_a_executar = num_arg # Usa o número passado se for válido
            else:
                print("Número de transações deve ser positivo. Usando o padrão.")
        except ValueError:
            # Se o argumento não for um número inteiro válido
            print("Argumento inválido para número de transações. Usando o padrão.")

    # Chama a função principal para iniciar a simulação com os parâmetros definidos
    main(num_a_executar, wait_a_usar)

