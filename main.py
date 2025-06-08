import threading
import time
import random
import sys

class GerenciadorRecursos:
    def __init__(self):
        self.recursos = {
            'X': {'lock_holder_id': None, 'lock_holder_timestamp': -1, 'waiting_transactions': []},
            'Y': {'lock_holder_id': None, 'lock_holder_timestamp': -1, 'waiting_transactions': []}
        }
        self.lock = threading.Lock()
        self.next_timestamp = 0

    def get_timestamp(self) -> int:
        with self.lock:
            timestamp = self.next_timestamp
            self.next_timestamp += 1
            return timestamp

    def request_lock(self, transaction_id: int, timestamp: int, item_id: str) -> str:
        with self.lock:
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
                     recurso['waiting_transactions'].sort(key=lambda x: x[1])
                return 'wait'
            else:
                return 'abort'

    def release_lock(self, transaction_id: int, item_id: str) -> bool:
        with self.lock:
            recurso = self.recursos[item_id]
            if recurso['lock_holder_id'] == transaction_id:
                recurso['lock_holder_id'] = None
                recurso['lock_holder_timestamp'] = -1
                return True
            else:
                return False

    def remove_from_wait_queues(self, transaction_id: int):
        with self.lock:
            for item_id in self.recursos:
                recurso = self.recursos[item_id]
                recurso['waiting_transactions'] = [
                    t for t in recurso['waiting_transactions'] if t[0] != transaction_id
                ]

class Transacao(threading.Thread):
    def __init__(self, t_id: int, gerenciador_recursos: GerenciadorRecursos, max_wait_time: float = 0.5):
        super().__init__(name=f"Transacao-{t_id}")
        self.t_id = t_id
        self.gerenciador_recursos = gerenciador_recursos
        self.max_wait_time = max_wait_time
        self.timestamp = -1
        self.aborted = threading.Event()
        self.locks_held = set()

    def run(self):
        self.timestamp = self.gerenciador_recursos.get_timestamp()
        print(f"T{self.t_id} (TS={self.timestamp}): Iniciando execução.")

        while True:
            self.aborted.clear()
            self.locks_held.clear()

            try:
                self.random_wait()
                if self.aborted.is_set(): continue

                if not self.acquire("X"):
                    self.release_all_held_locks()
                    time.sleep(random.uniform(0.1, 0.3))
                    print(f"T{self.t_id} (TS={self.timestamp}): Reiniciando após aborto ao tentar pegar X.")
                    continue

                self.random_wait()
                if self.aborted.is_set():
                   self.release_all_held_locks()
                   time.sleep(random.uniform(0.1, 0.3))
                   print(f"T{self.t_id} (TS={self.timestamp}): Reiniciando após aborto durante espera (tinha X).")
                   continue

                if not self.acquire("Y"):
                    self.release_all_held_locks()
                    time.sleep(random.uniform(0.1, 0.3))
                    print(f"T{self.t_id} (TS={self.timestamp}): Reiniciando após aborto ao tentar pegar Y (tinha X).")
                    continue

                self.random_wait()
                if self.aborted.is_set():
                    self.release_all_held_locks()
                    time.sleep(random.uniform(0.1, 0.3))
                    print(f"T{self.t_id} (TS={self.timestamp}): Reiniciando após aborto durante espera (tinha X, Y).")
                    continue

                self.release("X")

                self.random_wait()
                if self.aborted.is_set():
                    self.release_all_held_locks()
                    time.sleep(random.uniform(0.1, 0.3))
                    print(f"T{self.t_id} (TS={self.timestamp}): Reiniciando após aborto durante espera (tinha Y).")
                    continue

                self.release("Y")

                self.random_wait()

                print(f"T{self.t_id} (TS={self.timestamp}): Commitado com sucesso!")
                break

            except Exception as e:
                print(f"T{self.t_id} (TS={self.timestamp}): Erro inesperado: {e}. Abortando e reiniciando.")
                self.aborted.set()
                self.release_all_held_locks()
                time.sleep(random.uniform(0.2, 0.5))
                continue

        print(f"T{self.t_id} (TS={self.timestamp}): Finalizada.")

    def acquire(self, item_id: str) -> bool:
        while True:
            if self.aborted.is_set():
                return False

            print(f"T{self.t_id} (TS={self.timestamp}): Tentando adquirir lock em {item_id}...")
            status = self.gerenciador_recursos.request_lock(self.t_id, self.timestamp, item_id)

            if status == 'granted':
                print(f"T{self.t_id} (TS={self.timestamp}): Adquiriu lock em {item_id}.")
                self.locks_held.add(item_id)
                return True
            elif status == 'wait':
                holder_info = self.gerenciador_recursos.recursos[item_id]
                print(f"T{self.t_id} (TS={self.timestamp}): Esperando por lock em {item_id} (detido por T{holder_info['lock_holder_id']} TS={holder_info['lock_holder_timestamp']})...")
                wait_start = time.time()
                while time.time() - wait_start < 2.0:
                    if self.aborted.is_set():
                        return False
                    time.sleep(random.uniform(0.1, 0.3))
            elif status == 'abort':
                holder_info = self.gerenciador_recursos.recursos[item_id]
                print(f"T{self.t_id} (TS={self.timestamp}): ABORTADA (Wait-Die) ao tentar adquirir {item_id} (detido por T{holder_info['lock_holder_id']} TS={holder_info['lock_holder_timestamp']}).")
                self.aborted.set()
                self.gerenciador_recursos.remove_from_wait_queues(self.t_id)
                return False
            else:
                 print(f"T{self.t_id} (TS={self.timestamp}): Recebeu status inesperado '{status}' do gerenciador para {item_id}. Abortando.")
                 self.aborted.set()
                 self.gerenciador_recursos.remove_from_wait_queues(self.t_id)
                 return False

    def release(self, item_id: str):
        if item_id in self.locks_held:
            print(f"T{self.t_id} (TS={self.timestamp}): Liberando lock em {item_id}...")
            released = self.gerenciador_recursos.release_lock(self.t_id, item_id)
            if released:
                self.locks_held.remove(item_id)
                print(f"T{self.t_id} (TS={self.timestamp}): Lock em {item_id} liberado.")

    def release_all_held_locks(self):
        locks_to_release = list(self.locks_held)
        if locks_to_release:
            print(f"T{self.t_id} (TS={self.timestamp}): Liberando todos os locks detidos: {locks_to_release}")
            for item_id in locks_to_release:
                self.release(item_id)

    def random_wait(self):
        wait_time = random.uniform(0.1, self.max_wait_time)
        wait_start = time.time()
        while time.time() - wait_start < wait_time:
             if self.aborted.is_set():
                 break
             time.sleep(0.05)

NUM_TRANSACOES_PADRAO = 3
MAX_WAIT_TIME_TRANSACAO_PADRAO = 0.8

def main(num_transacoes, max_wait_time):
    print("--- Iniciando Simulação de Transações Concorrentes com Wait-Die ---")
    print(f"Número de Transações: {num_transacoes}")
    print(f"Recursos Compartilhados: X, Y")
    print("Técnica de Prevenção de Deadlock: Wait-Die")
    print("-----------------------------------------------------------------")

    gerenciador = GerenciadorRecursos()

    threads = []
    for i in range(1, num_transacoes + 1):
        transacao_thread = Transacao(t_id=i,
                                     gerenciador_recursos=gerenciador,
                                     max_wait_time=max_wait_time)
        threads.append(transacao_thread)

    print("\n--- Iniciando Threads ---")
    start_time = time.time()
    for thread in threads:
        thread.start()

    print("\n--- Aguardando Finalização das Threads ---")
    for thread in threads:
        thread.join()

    end_time = time.time()
    print("-----------------------------------------------------------------")
    print(f"--- Simulação Concluída em {end_time - start_time:.2f} segundos ---")

if __name__ == "__main__":
    num_a_executar = NUM_TRANSACOES_PADRAO
    wait_a_usar = MAX_WAIT_TIME_TRANSACAO_PADRAO

    if len(sys.argv) > 1:
        try:
            num_arg = int(sys.argv[1])
            if num_arg > 0:
                num_a_executar = num_arg
            else:
                print("Número de transações deve ser positivo. Usando o padrão.")
        except ValueError:
            print("Argumento inválido para número de transações. Usando o padrão.")

    main(num_a_executar, wait_a_usar)
