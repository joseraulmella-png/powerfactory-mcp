import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import diagramas
import servidor


class SolicitudesTest(unittest.TestCase):
    def test_respuesta_tardia_tras_vencimiento(self):
        with tempfile.TemporaryDirectory() as carpeta, patch.object(servidor, 'INTERCAMBIO', Path(carpeta)):
            identificador = servidor.crear_solicitud(timeout=-1, accion='ejecutar_python')
            peticion = Path(carpeta) / ('peticion_' + identificador + '.json')
            with self.assertRaisesRegex(TimeoutError, 'mismo id'):
                servidor.recoger_solicitud(identificador)
            self.assertTrue(peticion.exists())
            respuesta = Path(carpeta) / ('respuesta_' + identificador + '.json')
            respuesta.write_text(json.dumps({'id': identificador, 'ok': True, 'resultado': {'ejecutado': True}}), encoding='utf-8')
            peticion.unlink()
            self.assertEqual(servidor.recoger_solicitud(identificador), {'ejecutado': True})
            self.assertFalse(respuesta.exists())


class Objeto:
    def __init__(self, nombre, attrs=None):
        self.loc_name = nombre
        self.attrs = attrs or {}
        self.eliminado = False

    def GetFullName(self): return self.loc_name
    def GetClassName(self): return 'ElmLod'
    def GetAttribute(self, clave): return self.attrs.get(clave, '')
    def SetAttribute(self, clave, valor): self.attrs[clave] = valor
    def Delete(self): self.eliminado = True
    def GetContents(self, patron, recursivo):
        if patron == '*.SetVitxt': return [Objeto('texto')]
        if patron == '*.IntFormsel': return [Objeto('formulario')]
        return []


class Diagrama(Objeto):
    def __init__(self, elemento):
        super().__init__('diagrama')
        self.simbolo = Objeto('simbolo', {'pDataObj': elemento, 'rCenterX': 10, 'rCenterY': 10})
        self.plantilla = Objeto('plantilla', {'sSymNam': 'TBDummy', 'rCenterX': 0, 'rCenterY': 0})
        self.etiqueta = Objeto('TB_Nombre_carga')
        self.potencias = Objeto('TB_Potencias_carga')

    def GetContents(self, patron, recursivo):
        if patron == '*.IntGrf': return [self.simbolo, self.plantilla]
        if patron == 'TB_Nombre_carga.IntGrf': return [self.etiqueta]
        if patron == 'TB_Potencias_carga.IntGrf': return [self.potencias]
        return []

    def AddCopy(self, plantilla, nombre): return Objeto(nombre)


class AnotacionesTest(unittest.TestCase):
    def test_solo_se_reemplaza_lo_solicitado(self):
        for etiqueta, potencias in ((True, False), (False, True), (True, True), (False, False)):
            with self.subTest(etiqueta=etiqueta, potencias=potencias):
                elemento = Objeto('carga')
                dia = Diagrama(elemento)
                class Proyecto:
                    def GetContents(self, patron, recursivo): return [elemento]
                class App:
                    def GetActiveProject(self): return Proyecto()
                    def SetGraphicUpdate(self, valor): pass
                    def Rebuild(self, valor): pass
                with patch.object(diagramas, '_obtener_diagrama_activo', return_value=dia):
                    diagramas.anotar(App(), 'carga', etiqueta, potencias)
                self.assertEqual(dia.etiqueta.eliminado, etiqueta)
                self.assertEqual(dia.potencias.eliminado, potencias)


if __name__ == '__main__':
    unittest.main()
