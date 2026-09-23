"""Pagina de demo local para el motor etl_pmc.

IMPORTANTE: esto NO es parte del Container Apps Job. El Job sigue siendo un
batch/CLI puro (prompt seccion 1: sin FastAPI/Flask/ingress). Esta pagina es
una herramienta de desarrollo/demo aparte, pensada para correr en la maquina
de quien la usa (127.0.0.1), que llama al MISMO motor (`etl_pmc.pipeline.ejecutar`,
la misma funcion que usa `etl-pmc run`) sin modificar ni un archivo de `src/etl_pmc`.

No se instala en la imagen Docker: Flask esta en el extra opcional "demo" de
pyproject.toml, y el Dockerfile solo instala el paquete base ("pip install .",
sin extras).

Uso:
    pip install -e ".[demo]"
    python demo_ui/server.py
    -> abre http://127.0.0.1:5050
"""

from __future__ import annotations

import shutil
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

# Permite correr "python demo_ui/server.py" sin instalar el paquete primero,
# siempre que se haya corrido "pip install -e .[demo]" (que sí es requerido
# para tener Flask); esto solo agrega src/ al path para encontrar etl_pmc.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from etl_pmc.manifest import parsear_manifiesto  # noqa: E402
from etl_pmc.pipeline import ejecutar  # noqa: E402
from etl_pmc.storage.local import LocalStorageAdapter  # noqa: E402
from etl_pmc.tools.compare_adf import _CAMPOS_DETALLE  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
RUNS_DIR.mkdir(exist_ok=True)
EXAMPLES_DIR = BASE_DIR.parent / "examples"

app = Flask(__name__, static_folder="static", template_folder="templates")

# Estado de corridas en memoria (herramienta de demo de un solo proceso, sin
# persistencia entre reinicios -- no es un requisito de la POC).
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()

LOTE_ID = "LOTE_DEMO_UI"


def _construir_manifiesto_dict(job_id: str, run_dir: Path, *, nombre_txt: str, nombre_csv: str, parametros: dict) -> dict:
    return {
        "schema_version": "1.0",
        "run_id": f"demo-ui-{job_id}",
        "pipeline_run_id": f"demo-ui-{job_id}",
        "lote_id": LOTE_ID,
        "profile": "poc_pmc",
        "storage_account_url": "https://demo-local.invalid",
        "input": {"container": "inbound", "blob": f"sap/demo/{job_id}/{nombre_txt}", "etag": None},
        "enrichment": {
            "container": "enrichment",
            "blob": f"sap/demo/{job_id}/{nombre_csv}",
            "mode": "single_configuration",
        },
        "output": {"container": "out", "prefix": f"pmc/containerapp/demo/{job_id}", "filename": "FAC0001.demoui"},
        "audit": {"container": "audit", "prefix": f"containerapp/demo/{job_id}"},
        "errors": {"container": "error", "prefix": f"containerapp/demo/{job_id}"},
        "parameters": {
            "CodBancoPMC": "001",
            "CodigoServicioPMC": "0001",
            "TipoRegistroCabPMC": "0",
            "TipoRegistroDetPMC": "1",
            "TipoRegistroPiePMC": "9",
            "AplicarFiltro30Dias": parametros["aplicar_filtro_30_dias"],
            "AplicarMaxDosCliente": parametros["aplicar_max_dos_cliente"],
            "AplicarFiltroAntiguedad": parametros["aplicar_filtro_antiguedad"],
            "CuotaPMC": "01",
            "FechaEjecucionUTC": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "format": {
            "input_encoding": "utf-8",
            "output_encoding": "utf-8",
            "output_newline": "CRLF",
            "output_bom": False,
            "final_newline": True,
        },
    }


def _decodificar_lineas_preview(texto: str, cantidad: int = 5) -> list[dict]:
    """Decodifica las primeras 'cantidad' lineas de detalle del archivo de
    salida campo por campo, reusando las posiciones que ya usa compare-adf
    (etl_pmc.tools.compare_adf._CAMPOS_DETALLE) -- no duplica el layout.

    'texto' debe venir de decodificar BYTES crudos (nunca de un read_text()
    en modo texto): la traduccion de saltos de linea universal de Python
    convierte CRLF a LF al leer en modo texto, y el split por '\\r\\n' de
    abajo no encontraria nada."""
    lineas = [l for l in texto.split("\r\n") if l]
    if len(lineas) < 2:
        return []
    detalles = lineas[1:-1][:cantidad]
    preview = []
    for linea in detalles:
        campos = {}
        for nombre, inicio, largo in _CAMPOS_DETALLE:
            valor = linea[inicio - 1 : inicio - 1 + largo].strip()
            if valor:
                campos[nombre] = valor
        preview.append(campos)
    return preview


def _correr_job(job_id: str, run_dir: Path, manifiesto_dict: dict) -> None:
    inicio = time.monotonic()
    try:
        storage = LocalStorageAdapter(run_dir)
        manifiesto = parsear_manifiesto(manifiesto_dict)
        resultado = ejecutar(manifiesto, storage)

        preview = []
        salida_path = None
        if resultado.archivos_producidos:
            container, blob = resultado.archivos_producidos[0].split("/", 1)
            salida_path = run_dir / container / blob
            if salida_path.is_file():
                texto_salida = salida_path.read_bytes().decode(manifiesto.format.output_encoding)
                preview = _decodificar_lineas_preview(texto_salida)

        with _JOBS_LOCK:
            _JOBS[job_id].update(
                estado="listo",
                resultado=resultado.to_dict(),
                preview=preview,
                segundos_totales=time.monotonic() - inicio,
            )
    except Exception as exc:  # una corrida de demo no debe tirar abajo el server
        with _JOBS_LOCK:
            _JOBS[job_id].update(
                estado="error",
                error=f"{exc}",
                traceback=traceback.format_exc(),
                segundos_totales=time.monotonic() - inicio,
            )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ejecutar", methods=["POST"])
def ejecutar_endpoint():
    archivo_txt = request.files.get("archivo_txt")
    if archivo_txt is None or archivo_txt.filename == "":
        return jsonify({"error": "Falta el archivo TXT de entrada"}), 400

    job_id = uuid.uuid4().hex[:12]
    run_dir = RUNS_DIR / job_id
    (run_dir / "inbound" / "sap" / "demo" / job_id).mkdir(parents=True, exist_ok=True)
    (run_dir / "enrichment" / "sap" / "demo" / job_id).mkdir(parents=True, exist_ok=True)

    nombre_txt = archivo_txt.filename
    ruta_txt = run_dir / "inbound" / "sap" / "demo" / job_id / nombre_txt
    archivo_txt.save(ruta_txt)

    archivo_csv = request.files.get("archivo_csv")
    if archivo_csv is not None and archivo_csv.filename:
        nombre_csv = archivo_csv.filename
        ruta_csv = run_dir / "enrichment" / "sap" / "demo" / job_id / nombre_csv
        archivo_csv.save(ruta_csv)
    else:
        # Sin CSV propio: se usa el de ejemplo del repo (dato real de
        # GDC-1000: CodEntidad=324, "Pago Mis Cuentas"), para que se pueda
        # probar sin preparar nada de antemano.
        nombre_csv = "enrichment_single_configuration.example.csv"
        ruta_csv = run_dir / "enrichment" / "sap" / "demo" / job_id / nombre_csv
        shutil.copyfile(EXAMPLES_DIR / "enrichment_single_configuration.example.csv", ruta_csv)

    parametros = {
        "aplicar_filtro_30_dias": request.form.get("aplicar_filtro_30_dias") == "on",
        "aplicar_max_dos_cliente": request.form.get("aplicar_max_dos_cliente") == "on",
        "aplicar_filtro_antiguedad": request.form.get("aplicar_filtro_antiguedad") == "on",
    }
    manifiesto_dict = _construir_manifiesto_dict(
        job_id, run_dir, nombre_txt=nombre_txt, nombre_csv=nombre_csv, parametros=parametros
    )
    (run_dir / "manifiesto.json").write_text(
        __import__("json").dumps(manifiesto_dict, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    with _JOBS_LOCK:
        _JOBS[job_id] = {"estado": "corriendo", "inicio": time.monotonic(), "run_dir": str(run_dir)}

    hilo = threading.Thread(target=_correr_job, args=(job_id, run_dir, manifiesto_dict), daemon=True)
    hilo.start()

    return jsonify({"job_id": job_id})


@app.route("/estado/<job_id>")
def estado(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "job_id desconocido"}), 404
        respuesta = {
            "estado": job["estado"],
            "elapsed_seconds": time.monotonic() - job["inicio"] if job["estado"] == "corriendo" else job.get("segundos_totales"),
        }
        if job["estado"] == "listo":
            respuesta["resultado"] = job["resultado"]
            respuesta["preview"] = job["preview"]
        elif job["estado"] == "error":
            respuesta["error"] = job["error"]
    return jsonify(respuesta)


@app.route("/descargar/<job_id>/<tipo>")
def descargar(job_id: str, tipo: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None or job.get("estado") != "listo":
        return jsonify({"error": "la corrida no esta lista"}), 404

    run_dir = Path(job["run_dir"])
    resultado = job["resultado"]

    if tipo == "manifiesto":
        return send_file(run_dir / "manifiesto.json", as_attachment=True, download_name="manifiesto.json")
    if tipo == "resultado":
        import json

        ruta = run_dir / "resultado.json"
        ruta.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
        return send_file(ruta, as_attachment=True, download_name="resultado.json")
    if tipo == "salida":
        if not resultado["archivos_producidos"]:
            return jsonify({"error": "esta corrida no produjo archivo de salida"}), 404
        container, blob = resultado["archivos_producidos"][0].split("/", 1)
        ruta = run_dir / container / blob
        return send_file(ruta, as_attachment=True, download_name=Path(blob).name)
    if tipo == "errores":
        if not resultado.get("ruta_errores"):
            return jsonify({"error": "esta corrida no genero archivo de errores"}), 404
        container, blob = resultado["ruta_errores"].split("/", 1)
        ruta = run_dir / container / blob
        return send_file(ruta, as_attachment=True, download_name=Path(blob).name)

    return jsonify({"error": f"tipo de descarga desconocido: {tipo}"}), 400


if __name__ == "__main__":
    print("Demo local de etl_pmc -- NO es el Container Apps Job, solo una herramienta de desarrollo.")
    print("Abrir: http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=False)
