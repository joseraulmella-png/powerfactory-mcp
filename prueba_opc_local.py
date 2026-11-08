"""Prueba aislada OPC UA en bucle local; no conecta ni modifica PowerFactory."""
import asyncio
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / '.opc-deps'))
from asyncua import Client, Server, ua


async def main():
    with socket.socket() as reserva:
        reserva.bind(('127.0.0.1', 0))
        puerto = reserva.getsockname()[1]
    url = 'opc.tcp://127.0.0.1:%d/prueba/' % puerto
    server = Server()
    await server.init()
    server.set_endpoint(url)
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    indice = await server.register_namespace('urn:powerfactory-mcp:prueba-local')
    variable = await server.nodes.objects.add_variable(indice, 'Prueba', 1.0)
    await variable.set_writable()
    async with server:
        async with Client(url) as cliente:
            remota = cliente.get_node(variable.nodeid)
            assert await remota.read_value() == 1.0
            await remota.write_value(2.0)
            assert await variable.read_value() == 2.0
            print('OPC UA local: lectura y escritura de prueba correctas.')


if __name__ == '__main__':
    asyncio.run(main())
