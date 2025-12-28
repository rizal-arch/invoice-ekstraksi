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

# --- 2. SECURITY (Mengambil Kunci dari Brankas) ---
try:
    # Pastikan Anda sudah set NVIDIA_API_KEY di Streamlit Secrets
    NVIDIA_API_KEY = st.secrets["NVIDIA_API_KEY"]
except:
    st.error("⚠️ Kunci Brankas Hilang! Harap pasang 'NVIDIA_API_KEY' di Streamlit Secrets.")
    st.stop()

# --- 3. OTAK "FORENSIK" (PROMPT YANG DI-UPGRADE) ---
def process_single_invoice(image_file, api_key):
    # Encode gambar
    image_bytes = image_file.getvalue()
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

    # Mengambil tahun sekarang secara dinamis
    tahun_ini = datetime.now().year

    # Prompt "Auditor Galak"
    prompt = f"""
    PERAN: Kamu adalah Auditor Forensik & Matematikawan.
    TUGAS: Ekstrak & KOREKSI data dari invoice yang tulisannya buruk/rusak.
    
    KONTEKS WAKTU: Hari ini adalah tahun {tahun_ini}.
    
    ATURAN KOREKSI OTOMATIS (WAJIB DIPATUHI):
    
    1. 📅 PERBAIKAN TANGGAL (PRIORITAS TINGGI):
       - Masalah: Tahun sering tertulis coretan atau terpotong (misal: "17-12-2--", "25", "17 12 2").
       - SOLUSI: Jika digit tahun < 4 atau tidak jelas, ASUMSIKAN tahun {tahun_ini}.
       - Contoh: "17-12-2--" -> UBAH JADI "17-12-{tahun_ini}".
    
    2. 🧮 VALIDASI MATEMATIKA (LOGIC OVER VISION):
       - Lakukan Cross-Check: (Qty x Harga Satuan) HARUS SAMA DENGAN Total Baris.
       - Jika tulisan Harga sulit dibaca (misal "S000" atau "I0.000"), HITUNG MUNDUR: (Total / Qty).
       - Jika Total Invoice tertulis ngawur (misal 1.352.700 padahal item cuma 100rb), HITUNG ULANG dari penjumlahan item yang benar.
       - JANGAN PERCAYA OCR MENTAH jika matematikanya salah.
    
    3. 📝 PEMBERSIHAN DATA:
       - Hapus simbol aneh di nama barang.
       - Pastikan nama Vendor terbaca jelas.

    OUTPUT JSON FINAL:
    Hanya berikan JSON valid tanpa markdown '```'.
    {{
        "tanggal": "DD-MM-YYYY (Hasil koreksi)",
        "no_invoice": "String",
        "vendor": "String",
        "pembeli": "String",
        "items": [
            {{
                "nama_item": "String",
                "qty": Integer, 
                "harga_satuan": Integer (Hasil koreksi),
                "total": Integer (Hasil koreksi)
            }}
        ],
        "total_akhir": Integer (Hasil penjumlahan ulang yang benar),
        "catatan_audit": "Jelaskan perbaikan yang kamu lakukan (misal: 'Mengoreksi tahun 2-- menjadi {tahun_ini}')"
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
            temperature=0.1, # Rendah agar tidak halusinasi
            max_tokens=1024
        )
        content = response.choices[0].message.content
        
        # Bersihkan Markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
             content = content.split("```")[1].split("```")[0]
             
        data = json.loads(content)
        # Tempel nama file asli untuk tracking
        data['nama_file_asli'] = image_file.name 
        return data
        
    except Exception as e:
        return {"nama_file_asli": image_file.name, "catatan_audit": f"ERROR SYSTEM: {str(e)}"}

# --- 4. UI UTAMA (BATCH PROCESSING) ---
st.title("🕵️‍♂️ Invoice Auditor Pro (Batch)")
st.caption("Sistem ekstraksi cerdas dengan fitur 'Self-Correction' untuk tulisan tangan & kalkulasi otomatis.")

# Area Upload
uploaded_files = st.file_uploader(
    "Drop banyak invoice sekaligus di sini (JPG/PNG)", 
    type=["jpg", "jpeg", "png"], 
    accept_multiple_files=True
)

if uploaded_files:
    jumlah_file = len(uploaded_files)
    st.info(f"📂 {jumlah_file} dokumen siap diaudit.")
    
    if st.button(f"🚀 Mulai Audit {jumlah_file} File", type="primary"):
        
        all_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # --- PROSES LOOPING ---
        for i, file in enumerate(uploaded_files):
            status_text.text(f"⏳ Sedang mengaudit file {i+1}/{jumlah_file}: {file.name}...")
            
            # Panggil AI Forensik
            hasil = process_single_invoice(file, NVIDIA_API_KEY)
            
            # Flatten JSON (Agar Item masuk ke baris terpisah di Excel)
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
                        "Total Baris": item.get('total', 0),
                        "Total Invoice (Audit)": hasil.get('total_akhir', 0),
                        "Catatan Audit AI": hasil.get('catatan_audit', ''),
                        "Nama File": hasil.get('nama_file_asli', '')
                    }
                    all_results.append(row)
            else:
                # Jika format error/tidak ada item
                all_results.append(hasil)
            
            # Update Progress
            progress_bar.progress((i + 1) / jumlah_file)
            
        status_text.success("✅ Audit Selesai! Data siap didownload.")
        time.sleep(1)
        progress_bar.empty()
        
        # --- TAMPILAN & DOWNLOAD ---
        if all_results:
            df = pd.DataFrame(all_results)
            
            # Tampilkan Tabel Editor
            st.markdown("### 📝 Review Hasil Audit")
            edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
            
            # Tombol Download Excel
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                edited_df.to_excel(writer, index=False, sheet_name='AuditData')
                # Auto-adjust column width (Opsional visual)
                worksheet = writer.sheets['AuditData']
                for idx, col in enumerate(edited_df.columns):
                    series = edited_df[col]
                    max_len = max((series.astype(str).map(len).max(), len(str(col)))) + 1
                    worksheet.set_column(idx, idx, max_len)
                
            st.download_button(
                label="📥 Download Excel (.xlsx)",
                data=buffer.getvalue(),
                file_name=f"Hasil_Audit_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.ms-excel",
                type="primary"
            )
