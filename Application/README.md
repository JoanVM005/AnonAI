# AnonRad AI

Aplicacion local para anonimizar radiografias usando el modelo YOLO entrenado del proyecto.

## Privacidad

- El procesamiento se realiza en local.
- La app solo guarda PNGs anonimizados o un ZIP final con PNGs anonimizados.
- No guarda JSON, previews ni historial persistente.
- No modifica las imagenes originales.
- La redaccion usa siempre `blur_then_black`: se aplica blur como paso intermedio y despues se sobrescriben los pixeles con negro.
- Los archivos temporales se eliminan al finalizar o al cancelar el guardado.
- OCR no guarda el texto reconocido; solo usa coincidencias temporales para tapar cajas adicionales.

## Instalacion

```bash
cd Application
pip install -r requirements.txt
```

## Ejecucion

Para demo local con doble click:

- macOS: `AnonRadAI.command`
- Linux: `AnonRadAI.sh`
- Windows: `AnonRadAI.bat`

Estos lanzadores crean un entorno local `.anonrad_env` la primera vez, instalan dependencias y abren la aplicacion. La primera ejecucion puede tardar.

Ejecucion manual para desarrollo:

```bash
python src/app.py
```

La app permite:

- hacer click en la zona de carga para seleccionar una o varias imagenes PNG, JPEG/JPG, DICOM o ZIP;
- seleccionar una carpeta con imagenes desde el mismo control;
- arrastrar imagenes, ZIPs o carpetas sobre la zona de carga si `tkinterdnd2` esta instalado;
- elegir que campos detectados por YOLO se anonimizan: nombre, identificador, edad, fecha y hora;
- mantener reglas OCR editables para tapar texto adicional cuando coincida con una regex activada;
- procesar localmente y guardar el resultado al finalizar.

Si procesas una sola imagen, la app te pedira donde guardar el PNG anonimizado.
Si procesas varias imagenes, una carpeta o un ZIP, la app te pedira donde guardar un ZIP con los PNGs anonimizados.

Formatos soportados de entrada:

- `.png`
- `.jpg` / `.jpeg`
- `.dcm` / `.dicom`
- `.zip` con cualquiera de los formatos anteriores dentro

Los archivos no soportados o corruptos no bloquean el lote: se omiten y aparecen en el resumen en pantalla. Si no se puede procesar ninguna imagen valida, la app muestra una alerta.

Los DICOM se leen como imagen para generar un PNG anonimizado. La escritura de un DICOM anonimizado queda fuera de esta fase porque requiere anonimizar tambien metadatos clinicos y validar el `pixel data`.

El padding esta en **Ajustes especiales** para evitar cambios accidentales.
La confianza del detector queda fija internamente en `0.25`.
Todos los campos vienen activados por defecto. Si se desactivan todos, la app no permite procesar.

## Reglas OCR

Las reglas OCR se guardan en:

```text
Application/config/ocr_rules.json
```

Cada regla tiene:

- `name`: nombre visible de la regla.
- `pattern`: regex usada para validar el texto OCR.
- `enabled`: si la regla se aplica o no.

Desde la app se pueden anadir, editar, activar/desactivar y eliminar reglas. OCR solo tapa texto cuando una regla activada coincide. La primera ejecucion de EasyOCR puede descargar sus pesos si no estan cacheados localmente.

## Distribucion Para Usuarios Finales

Para medicos o personal de gestion de imagenes, la opcion recomendada es entregar una app empaquetada, sin pedir Python ni terminal:

- **macOS**: generar `AnonRad AI.app` con PyInstaller o Briefcase y distribuirlo en un `.dmg`.
- **Windows**: generar `AnonRad AI.exe` con PyInstaller y crear instalador con Inno Setup o MSIX.
- **Linux**: generar AppImage o paquete `.deb` segun el hospital/entorno.

Para el hackathon, los lanzadores `AnonRadAI.command`, `AnonRadAI.sh` y `AnonRadAI.bat` son una solucion intermedia rapida. Para produccion, empaquetar la app junto con pesos YOLO, recursos, reglas OCR y pesos OCR cacheados evita descargas y pasos tecnicos.

## CLI opcional

```bash
python src/anonymize_radiograph.py \
  --input test_images/input \
  --output test_images/output/private_cli \
  --padding 0.10 \
  --conf 0.25 \
  --fields name,id,age,date,time \
  --ocr-rules config/ocr_rules.json \
  --no-json \
  --device cpu
```
