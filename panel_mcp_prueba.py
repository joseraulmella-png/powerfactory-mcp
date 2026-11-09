"""Panel experimental: parada limpia; reactivacion aun sin implementar."""
import json
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

INTERCAMBIO = Path(__file__).resolve().parent / 'intercambio'


def escucha_activa():
    try:
        latido = json.loads((INTERCAMBIO / 'latido_timer.json').read_text(encoding='utf-8'))
        return time.time() - float(latido['latido_unix']) < 3.5
    except (OSError, ValueError, KeyError, TypeError):
        return False


def detener():
    try:
        INTERCAMBIO.mkdir(exist_ok=True)
        (INTERCAMBIO / 'detener_timer').touch()
    except OSError as error:
        messagebox.showerror('MCP', 'No se pudo solicitar la parada: ' + str(error))


def activar():
    messagebox.showinfo('MCP', 'La reactivacion directa todavia no esta implementada.')


ventana = tk.Tk()
ventana.title('Control MCP - prueba')
ventana.resizable(False, False)
ventana.attributes('-topmost', True)
estado = tk.StringVar(value='Comprobando escucha...')
tk.Label(ventana, textvariable=estado, padx=20, pady=12).pack()
tk.Button(ventana, text='Desactivar escucha', command=detener, width=26).pack(padx=20, pady=4)
tk.Button(ventana, text='Activar escucha (pendiente)', command=activar, width=26).pack(padx=20, pady=(4, 15))


def actualizar():
    estado.set('Escucha activa' if escucha_activa() else 'Escucha no detectada')
    ventana.after(1000, actualizar)


actualizar()
ventana.mainloop()
