import os
import signal
import subprocess


def kill_processes_by_name(names):
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        lines = result.stdout.split('\n')

        for line in lines:
            if any(name in line for name in names):
                parts = line.split()
                if len(parts) > 1:
                    pid = parts[1]
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                        print(f"Processo {pid} ({parts[-1]}) finalizado.")
                    except PermissionError:
                        print(f"Permissão negada para matar o processo {pid}. Tentando com sudo...")
                        subprocess.run(['sudo', 'kill', '-9', pid])
                    except ProcessLookupError:
                        print(f"Processo {pid} já não está em execução.")
    except Exception as e:
        print(f"Erro ao finalizar processos: {e}")


if __name__ == "__main__":
    process_names = [
        "core_back.py",
        "defeitos_deteccao.py",
        "scrcpy",
        "adb",
        "ffmpeg"
    ]
    kill_processes_by_name(process_names)
