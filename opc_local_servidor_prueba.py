"""Servidor OPC UA temporal de prueba, limitado al loopback de este PC."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / '.opc-deps'))
from asyncua import Server, ua


async def main():
    server = Server()
    await server.init()
    server.set_endpoint('opc.tcp://127.0.0.1:4842/freeopcua/server/')
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    indice = await server.register_namespace('urn:powerfactory-mcp:prueba-local')
    valor = await server.nodes.objects.add_variable(indice, 'MCP_Prueba', 1.0)
    await valor.set_writable()
    async with server:
        print('Servidor de prueba disponible solo en 127.0.0.1.', flush=True)
        await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(main())
