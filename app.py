import streamlit as st
import pandas as pd
from openai import OpenAI
import base64
import json
import io
import time
from datetime import datetime

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Invoice Auditor AI", page_icon="🕵️‍♂️", layout="wide")

# --- 2. SECURITY ---
try:
    NVIDIA_API_KEY = st.secrets["NVIDIA_API_KEY"]
except:
    st.error("⚠️ Kunci Brankas Hilang! Harap pasang 'NVIDIA_API_KEY' di Streamlit Secrets.")
    st.stop()

# --- 3. OTAK FORENSIK (SAMA SEPERTI SEBELUMNYA) ---
def process_single_invoice(image_file, api_key):
    image_bytes = image_file.getvalue()
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

    tahun_ini = datetime.now().year

    prompt = f"""
    PERAN: Kamu adalah Auditor Forensik & Matematikawan.
    TUGAS: Ekstrak & KOREKSI data dari invoice.
    KONTEKS WAKTU: Hari ini tahun {tahun_ini}.
    
    ATURAN KOREKSI:
    1. 📅 TANGGAL: Jika tahun < 4 digit/coretan, ASUMSIKAN tahun {tahun_ini}.
    2. 🧮 MATEMATIKA: 
       - Wajib: (Qty x Harga Satuan) = Total Baris.
       - Jika Harga tidak terbaca, hitung: Total / Qty.
    3. 📝 BERSIHKAN simbol aneh.

    OUTPUT JSON FINAL:
    {{
        "tanggal": "DD-MM-YYYY",
        "no_invoice": "String",
        "vendor": "String",
        "pembeli": "String",
        "items": [
            {{
                "nama_item": "String",
                "qty": Integer, 
                "harga_satuan": Integer,
                "total": Integer
            }}
        ],
        "catatan_audit": "Catatan jika ada koreksi"
    }}
    """

    try:
        response = client.chat.completions.create(
            model="google/gemma-3-27b-it", 
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }],
            temperature=0.1,
            max_tokens=1024
        )
        content = response.choices[0].message.content
        if "```json" in content: content = content.split("```json")[1].split("```")[0]
        elif "```" in content: content = content.split("```")[1].split("```")[0]
        data = json.loads(content)
        data['nama_file_asli'] = image_file.name 
        return data
    except Exception as e:
        return {"nama_file_asli": image_file.name, "catatan_audit": f"ERROR: {str(e)}"}

# --- 4. UI UTAMA ---
st.title("🕵️‍♂️ Invoice Auditor Pro")
st.caption("Batch Processing • Auto-Correction • Grand Total • One-Click Copy")

uploaded_files = st.file_uploader("Drop invoice di sini", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files:
    if st.button(f"🚀 Proses {len(uploaded_files)} File", type="primary"):
        all_results = []
        progress_bar = st.progress(0)
        
        for i, file in enumerate(uploaded_files):
            hasil = process_single_invoice(file, NVIDIA_API_KEY)
            
            # Flatten JSON ke Baris Excel
            if 'items' in hasil and isinstance(hasil['items'], list):
                for item in hasil['items']:
                    row = {
                        "Tanggal": hasil.get('tanggal', ''),
                        "No Invoice": hasil.get('no_invoice', ''),
                        "Vendor": hasil.get('vendor', ''),
                        "Pembeli": hasil.get('pembeli', ''),
                        "Nama Barang": item.get('nama_item', ''),
                        "Qty": item.get('qty', 0),
                        "Harga Satuan": item.get('harga_satuan', 0),
                        "Total Baris": item.get('total', 0), # Kolom yang akan dijumlah
                        "Catatan": hasil.get('catatan_audit', ''),
                        "File": hasil.get('nama_file_asli', '')
                    }
                    all_results.append(row)
            else:
                all_results.append(hasil)
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        progress_bar.empty()
        
        if all_results:
            df = pd.DataFrame(all_results)
            
            # --- FITUR 1: HITUNG GRAND TOTAL ---
            total_semua = df['Total Baris'].sum()
            
            # Buat baris Grand Total (kosongkan kolom lain, isi Total Baris)
            grand_total_row = {k: '' for k in df.columns}
            grand_total_row['Nama Barang'] = 'GRAND TOTAL'
            grand_total_row['Total Baris'] = total_semua
            
            # Gabungkan ke DataFrame utama (untuk tampilan)
            df_display = pd.concat([df, pd.DataFrame([grand_total_row])], ignore_index=True)
            
            st.success("✅ Selesai!")
            
            # Tampilkan Tabel
            st.markdown("### 📝 Tabel Hasil & Edit")
            edited_df = st.data_editor(df_display, num_rows="dynamic", use_container_width=True)
            
            # --- FITUR 2: COPY PASTE (One-Click) ---
            st.markdown("### 📋 Salin Data (Untuk Paste ke Excel/Sheets)")
            st.caption("Klik tombol 'Copy' kecil di pojok kanan atas kotak hitam di bawah ini, lalu Paste (Ctrl+V) di Excel Anda.")
            
            # Konversi ke TSV (Tab Separated) agar rapi saat dipaste
            tsv_data = edited_df.to_csv(index=False, sep='\t')
            st.code(tsv_data, language='text')

            # --- FITUR 3: DOWNLOAD FILE ---
            st.markdown("### 📥 Download File")
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                edited_df.to_excel(writer, index=False, sheet_name='Data')
            
            st.download_button(
                label="Download Excel (.xlsx)",
                data=buffer.getvalue(),
                file_name="Hasil_Audit_Invoice.xlsx",
                mime="application/vnd.ms-excel"
            )
