"""Consulta la carga MCP al app-server de Codex sin crear chats."""
import json
import queue
import subprocess
import threading
import time


def main():
    proc = subprocess.Popen(['codex', 'app-server'], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8')
    lineas = queue.Queue()
    def leer():
        for linea in proc.stdout:
            lineas.put(linea)
    threading.Thread(target=leer, daemon=True).start()
    def enviar(mensaje):
        proc.stdin.write(json.dumps(mensaje) + '\n')
        proc.stdin.flush()
    def respuesta(identificador):
        limite = time.monotonic() + 25
        while time.monotonic() < limite:
            try:
                item = json.loads(lineas.get(timeout=max(0.1, limite-time.monotonic())))
            except queue.Empty:
                break
            if item.get('id') == identificador:
                return item
        raise TimeoutError('Codex no respondio a la verificacion.')
    try:
        enviar({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'pf-check', 'version': '1'}}})
        respuesta(1)
        enviar({'method': 'initialized'})
        enviar({'id': 2, 'method': 'mcpServerStatus/list', 'params': {'serverName': 'powerfactory_contexto'}})
        print(json.dumps(respuesta(2), ensure_ascii=False))
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == '__main__':
    main()
