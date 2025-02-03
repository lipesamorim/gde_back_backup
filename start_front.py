import docker
import subprocess
import os
import signal
import time
import webbrowser  # Módulo para abrir o navegador

# Inicializa o cliente Docker
client = docker.from_env()

# Containers que precisam ser verificados
containers_to_check = {
    "rabbitmq": "rabbitmq:3.13-management",
    "postgres": "postgres"
}


# Defina as variáveis de ambiente para os caminhos
# os.environ["FRONTEND_PATH"] = "/home/gde/Projeto/gde-insp-embalagem"
os.environ["FRONTEND_PATH"] = "/home/amorim/PycharmProjects/gde-insp-embalagem"

# os.environ["WEBSOCKET_PATH"] = "/home/gde/Projeto/gde-insp-embalagem/websocket-mq-server"
os.environ["WEBSOCKET_PATH"] = "/home/amorim/PycharmProjects/gde-insp-embalagem/websocket-mq-server"

# Função para verificar e iniciar containers
def check_and_start_containers():
    for name, image in containers_to_check.items():
        try:
            # Procura o container pelo nome
            container = client.containers.list(all=True, filters={"name": name})
            if not container:
                print(f"Container {name} não encontrado.")
                continue

            container = container[0]

            # Verifica o status do container
            if container.status != "running":
                print(f"Container {name} não está em execução. Iniciando...")
                container.start()
                print(f"Container {name} iniciado com sucesso.")
            else:
                print(f"Container {name} já está em execução.")
        except Exception as e:
            print(f"Erro ao verificar ou iniciar o container {name}: {e}")


# Função para liberar uma porta
def liberar_porta(porta):
    try:
        # Verifica se há algum processo ocupando a porta
        resultado = subprocess.check_output(["lsof", "-ti", f":{porta}"], text=True).strip()
        if resultado:
            # Finaliza os processos encontrados
            pids = resultado.splitlines()
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGKILL)  # Usa SIGKILL para forçar o encerramento
                    print(f"Processo {pid} na porta {porta} finalizado.")
                except Exception as e:
                    print(f"Erro ao finalizar processo {pid}: {e}")
        else:
            print(f"Nenhum processo encontrado na porta {porta}.")
    except subprocess.CalledProcessError:
        # Nenhum processo encontrado na porta
        print(f"Nenhum processo encontrado na porta {porta}.")
    except FileNotFoundError:
        print("O comando 'lsof' não foi encontrado. Certifique-se de que está instalado.")


# Função para iniciar o front-end
def iniciar_front():
    try:
        print("Liberando a porta 3000...")
        liberar_porta(3000)
        print("Liberando a porta 3001...")
        liberar_porta(3001)

        print("Iniciando o front-end...")
        # Usa a variável de ambiente para o caminho do projeto principal
        caminho_projeto = os.environ.get("FRONTEND_PATH")

        if not caminho_projeto:
            raise ValueError("A variável de ambiente FRONTEND_PATH não foi definida.")

        # Inicia o comando yarn dev no terminal
        subprocess.Popen(
            ["gnome-terminal", "--", "bash", "-c", f"cd {caminho_projeto} && yarn dev; exec bash"],
            preexec_fn=os.setsid
        )
        print("yarn dev iniciado no terminal.")

        # Aguarda o 'yarn dev' iniciar
        time.sleep(10)

        print("Iniciando o WebSocket...")
        # Usa a variável de ambiente para o caminho do WebSocket
        caminho_websocket = os.environ.get("WEBSOCKET_PATH")

        if not caminho_websocket:
            raise ValueError("A variável de ambiente WEBSOCKET_PATH não foi definida.")

        # Inicia o comando yarn start no terminal
        subprocess.Popen(
            ["gnome-terminal", "--", "bash", "-c", f"cd {caminho_websocket} && yarn start; exec bash"],
            preexec_fn=os.setsid
        )
        print("yarn start iniciado no terminal.")

        # Abre o navegador automaticamente no endereço localhost
        print("Abrindo o navegador em http://localhost:3000/")
        webbrowser.open("http://localhost:3000/")

    except Exception as e:
        print(f"Erro ao iniciar o front-end: {e}")


if __name__ == "__main__":
    print("Verificando e iniciando containers...")
    check_and_start_containers()

    print("Liberando as portas e iniciando o front-end...")
    iniciar_front()
