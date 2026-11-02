from datetime import datetime
import re
import sqlite3
from bs4 import BeautifulSoup
import pandas as pd
import requests
import streamlit as st

# Configuración de página con identidad Foxconn [FX]
st.set_page_config(
    page_title="Control de Inventario WIP - Foxconn", 
    page_icon="🏭",  
    layout="wide"
)

DB_FILE = "inventario_wip.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario (
            ppid TEXT PRIMARY KEY,
            tipo_tarjeta TEXT,
            columna TEXT,
            nivel_espacio TEXT,
            model_name TEXT,
            next_station TEXT,
            revision TEXT,
            mo_number TEXT,
            fecha_entrada TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT,
            ppid TEXT,
            tipo_tarjeta TEXT,
            ubicacion TEXT,
            model_name TEXT,
            mo_number TEXT,
            fecha_hora TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


def consultar_flujo_web(ppid):
    res = {
        "model_name": "N/D",
        "next_station": "N/D",
        "revision": "N/D",
        "mo_number": "N/D",
    }
    ppid_buscado = str(ppid).strip().upper()
    url = "http://10.12.172.228/flujo/"
    
    response = None
    try:
        for campo in ["serial", "barcode", "txtSerial", "ppid"]:
            try:
                resp = requests.post(url, data={campo: ppid_buscado}, timeout=2)
                if resp.status_code == 200 and len(resp.text) > 300:
                    response = resp
                    break
            except:
                pass
        
        if not response:
            for param in ["serial", "barcode", "txtSerial", "ppid"]:
                try:
                    resp = requests.get(url, params={param: ppid_buscado}, timeout=2)
                    if resp.status_code == 200 and len(resp.text) > 300:
                        response = resp
                        break
                except:
                    pass

        if response and response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            texto_pagina = soup.get_text()

            mo_match = re.search(r'Work\s*Order\s*[:\s]*([A-Za-z0-9_-]+)', texto_pagina, re.IGNORECASE)
            if mo_match:
                res["mo_number"] = mo_match.group(1).strip()

            model_match = re.search(r'Model\s*Name\s*[:\s]*([A-Za-z0-9_-]+)', texto_pagina, re.IGNORECASE)
            if model_match:
                res["model_name"] = model_match.group(1).strip()

            rev_match = re.search(r'Version\s*Code\s*[:\s]*([A-Za-z0-9-]+)', texto_pagina, re.IGNORECASE)
            if rev_match:
                rev_val = rev_match.group(1).strip()
                rev_val = re.sub(r'Container.*$', '', rev_val, flags=re.IGNORECASE).strip()
                res["revision"] = rev_val

            station_match = re.search(r'Next\s*group\s*[:\s]*([A-Za-z0-9_-]+)', texto_pagina, re.IGNORECASE)
            if station_match:
                res["next_station"] = station_match.group(1).strip()
            else:
                station_match2 = re.search(r'Station\s*[:\s]*([A-Za-z0-9_-]+)', texto_pagina, re.IGNORECASE)
                if station_match2:
                    res["next_station"] = station_match2.group(1).strip()

    except Exception:
        pass

    return res


# ---------------------------------------------------------
# ENCABEZADO CON LOGOTIPO DE FOXCONN EN LA INTERFAZ
# ---------------------------------------------------------
col_logo, col_titulo = st.columns([1, 8])

with col_logo:
    try:
        st.image("foxconn_logo.png", width=90)
    except:
        st.markdown("### 🏭 **[FX]**")

with col_titulo:
    st.markdown("### Foxconn - Sistema de Control de Inventario WIP")

tab_entradas, tab_salidas, tab_inventario, tab_busqueda, tab_historial = st.tabs([
    "📥 Entradas",
    "📤 Salidas",
    "📊 Inventario Actual",
    "🔍 Buscar / Consultar",
    "📜 Historial",
])

# ---------------------------------------------------------
# 1. ENTRADAS
# ---------------------------------------------------------
with tab_entradas:
    st.subheader("Registro de Entradas de Material - Escaneo Continuo")
    
    col_tipo, col_columna = st.columns(2)
    with col_tipo:
        tipo_tarjeta = st.selectbox("Seleccione Tipo de Tarjeta:", ["PCB", "PCARD"], key="tipo_tarjeta_input")
        
    if tipo_tarjeta == "PCB":
        columnas_pcb = [f"{i}A" for i in range(1, 45)] + [f"{i}B" for i in range(1, 45)]
        with col_columna:
            columna_sel = st.selectbox("Seleccione Columna:", columnas_pcb, key="columna_pcb_sel")
        limite_espacios = 25
    else:  
        with col_columna:
            columna_sel = st.text_input("Ubicación / Rack (PCARD):", value="Rack-General", key="rack_pcard_input")
        limite_espacios = 500

    conn_db = sqlite3.connect(DB_FILE)
    cursor_db = conn_db.cursor()
    cursor_db.execute("SELECT nivel_espacio, ppid FROM inventario WHERE columna = ?", (columna_sel,))
    ocupados_dict = {str(row[0]): row[1] for row in cursor_db.fetchall()}
    conn_db.close()

    siguiente_nivel = None
    for n in range(1, limite_espacios + 1):
        if str(n) not in ocupados_dict:
            siguiente_nivel = str(n)
            break

    st.markdown("---")
    if siguiente_nivel:
        st.info(f"📍 **Ubicación Activa:** Columna **{columna_sel}** ➔ **Siguiente Nivel Disponible: Nivel {siguiente_nivel}**")
        
        with st.form(key="form_escaneo", clear_on_submit=True):
            ppid_entrada = st.text_input(
                f"Escanee el PPID para el Nivel {siguiente_nivel}:",
                key="input_ppid_escaneo"
            )
            
            # Campos opcionales de respaldo por si la red interna no responde desde la nube
            col_m, col_s, col_mo = st.columns(3)
            with col_m:
                manual_model = st.text_input("Modelo (Opcional):", value="", placeholder="Ej. LEO-PCB")
            with col_s:
                manual_station = st.text_input("Estación (Opcional):", value="", placeholder="Ej. SMT-01")
            with col_mo:
                manual_mo = st.text_input("MO Number (Opcional):", value="", placeholder="Ej. MO123456")

            submit_button = st.form_submit_button(label="Registrar Entrada")

        if submit_button and ppid_entrada:
            ppid_clean = ppid_entrada.strip().upper().split()[-1] if len(ppid_entrada.strip()) > 30 else ppid_entrada.strip().upper()
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute("SELECT ppid FROM inventario WHERE UPPER(TRIM(ppid)) = ?", (ppid_clean,))
            existe_ppid = cursor.fetchone()

            cursor.execute("SELECT ppid FROM inventario WHERE columna = ? AND nivel_espacio = ?", (columna_sel, siguiente_nivel))
            existe_ubicacion = cursor.fetchone()

            if existe_ppid:
                st.warning(f"⚠️ El PPID **{ppid_clean}** ya se encuentra registrado en el inventario.")
                conn.close()
            elif existe_ubicacion:
                st.error(f"❌ El Nivel {siguiente_nivel} ya fue ocupado.")
                conn.close()
            else:
                datos = consultar_flujo_web(ppid_clean)
                
                # Prioridad a los datos ingresados manualmente si la red interna no responde
                if manual_model.strip():
                    datos["model_name"] = manual_model.strip().upper()
                if manual_station.strip():
                    datos["next_station"] = manual_station.strip().upper()
                if manual_mo.strip():
                    datos["mo_number"] = manual
