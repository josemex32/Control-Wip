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

    # Si por restricciones de red en la nube no se obtuvo el modelo, asignamos un respaldo temporal basado en el PPID o genérico para pruebas
    if res["model_name"] == "N/D":
        res["model_name"] = "MODELO-FOXCONN"
    if res["next_station"] == "N/D":
        res["next_station"] = "SMT-LINE"
    if res["mo_number"] == "N/D":
        res["mo_number"] = "MO-DEFAULT"

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
                fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ubicacion_str = f"Col: {columna_sel} / Espacio: {siguiente_nivel}"

                cursor.execute(
                    """
                        INSERT INTO inventario (ppid, tipo_tarjeta, columna, nivel_espacio, model_name, next_station, revision, mo_number, fecha_entrada)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ppid_clean,
                        tipo_tarjeta,
                        columna_sel,
                        siguiente_nivel,
                        datos["model_name"],
                        datos["next_station"],
                        datos["revision"],
                        datos["mo_number"],
                        fecha_actual,
                    ),
                )
                cursor.execute(
                    """
                        INSERT INTO historial (tipo, ppid, tipo_tarjeta, ubicacion, model_name, mo_number, fecha_hora)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ENTRADA",
                        ppid_clean,
                        tipo_tarjeta,
                        ubicacion_str,
                        datos["model_name"],
                        datos["mo_number"],
                        fecha_actual,
                    ),
                )
                conn.commit()
                conn.close()

                st.success(f"✅ Registrado: **{ppid_clean}** | Modelo: **{datos['model_name']}** | MO: **{datos['mo_number']}** | Estación: **{datos['next_station']}**")
                st.rerun()
    else:
        st.error(f"❌ La columna/ubicación **{columna_sel}** está completamente llena.")

    with st.expander(f"Ver estado actual de la columna {columna_sel}"):
        if ocupados_dict:
            df_col_status = pd.DataFrame(list(ocupados_dict.items()), columns=["Nivel / Espacio", "PPID Ocupado"])
            df_col_status["Nivel_Num"] = pd.to_numeric(df_col_status["Nivel / Espacio"], errors="coerce")
            df_col_status = df_col_status.sort_values("Nivel_Num").drop(columns=["Nivel_Num"])
            st.dataframe(df_col_status, use_container_width=True)
        else:
            st.info("Esta columna está completamente vacía.")

# ---------------------------------------------------------
# 2. SALIDAS
# ---------------------------------------------------------
with tab_salidas:
    st.subheader("Registro de Salidas de Material")
    
    with st.form(key="form_salida", clear_on_submit=True):
        ppid_salida = st.text_input(
            "Escanee o ingrese el PPID para SALIDA (se borrará del inventario):",
            key="input_salida_form",
        )
        submit_salida = st.form_submit_button(label="Procesar Salida")

    if submit_salida and ppid_salida:
        ppid_raw = ppid_salida.strip().upper()
        ppid_clean = ppid_raw.split()[-1] if len(ppid_raw) > 30 else ppid_raw

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT model_name, mo_number, tipo_tarjeta, columna, nivel_espacio, ppid FROM inventario WHERE UPPER(TRIM(ppid)) = ?", (ppid_clean,))
        row = cursor.fetchone()

        if row:
            model_name, mo_number, tipo_tarjeta, columna, nivel_espacio, ppid_encontrado = row
            fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ubicacion_str = f"Col: {columna} / Espacio: {nivel_espacio}"

            cursor.execute("DELETE FROM inventario WHERE ppid = ?", (ppid_encontrado,))
            cursor.execute(
                """
                    INSERT INTO historial (tipo, ppid, tipo_tarjeta, ubicacion, model_name, mo_number, fecha_hora)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("SALIDA", ppid_encontrado, tipo_tarjeta, ubicacion_str, model_name, mo_number, fecha_actual),
            )
            conn.commit()
            conn.close()
            st.success(f"OUT: PPID **{ppid_encontrado}** dado de salida y liberado de [{ubicacion_str}].")
            st.rerun()
        else:
            conn.close()
            st.warning(f"⚠️ El PPID **{ppid_clean}** no existe actualmente en el inventario.")

# ---------------------------------------------------------
# 3. INVENTARIO ACTUAL
# ---------------------------------------------------------
with tab_inventario:
    st.subheader("Estado Actual del Inventario WIP")
    conn = sqlite3.connect(DB_FILE)
    df_inv = pd.read_sql_query("SELECT * FROM inventario", conn)
    conn.close()

    if not df_inv.empty:
        st.metric("Total de Unidades en WIP", len(df_inv))
        
        st.markdown("### 📊 Resumen Dinámico: Total por Modelo y Estación")
        
        df_resumen = (
            df_inv.groupby(["model_name", "next_station"])["ppid"]
            .count()
            .reset_index(name="QTY")
            .rename(columns={"model_name": "Model_Name", "next_station": "Next_Station"})
            .sort_values(by="QTY", ascending=False)
        )
        
        st.dataframe(df_resumen, use_container_width=True)
        st.markdown("---")

        st.subheader("Detalle Completo del Inventario")
        st.dataframe(df_inv, use_container_width=True)
    else:
        st.info("ℹ️ El inventario está actualmente vacío.")

# ---------------------------------------------------------
# 4. BÚSQUEDA / CONSULTAS
# ---------------------------------------------------------
with tab_busqueda:
    st.subheader("Buscar Unidades en Inventario")
    b_ppid = st.text_input("Filtrar por PPID:", key="filtro_busq_ppid")
    conn = sqlite3.connect(DB_FILE)
    query = "SELECT * FROM inventario WHERE 1=1"
    params = []
    if b_ppid:
        query += " AND ppid LIKE ?"
        params.append(f"%{b_ppid.strip().upper()}%")
    df_busqueda = pd.read_sql_query(query, conn, params=params)
    conn.close()
    st.dataframe(df_busqueda, use_container_width=True)

# ---------------------------------------------------------
# 5. HISTORIAL
# ---------------------------------------------------------
with tab_historial:
    st.subheader("Historial de Entradas y Salidas")
    conn = sqlite3.connect(DB_FILE)
    df_hist = pd.read_sql_query("SELECT * FROM historial ORDER BY id DESC", conn)
    conn.close()
    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True)
    else:
        st.info("ℹ️ No hay movimientos registrados todavía")
