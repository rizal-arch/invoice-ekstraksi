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

# --- 2. SECURITY (KUNCI BRANKAS) ---
try:
    NVIDIA_API_KEY = st.secrets["NVIDIA_API_KEY"]
except:
    st.error("⚠️ Kunci Brankas Hilang! Harap pasang 'NVIDIA_API_KEY' di Streamlit Secrets.")
    st.stop()

# --- 3. OTAK FORENSIK (PROMPT FINAL) ---
def process_single_invoice(image_file, api_key):
    # Encode gambar ke Base64
    image_bytes = image_file.getvalue()
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

    tahun_ini = datetime.now().year

    # Prompt yang sudah dipertajam untuk deteksi Vendor & Matematika
    prompt = f"""
    PERAN: Kamu adalah Auditor Forensik & Akuntan Senior.
    TUGAS: Ekstrak & KOREKSI data dari invoice yang mungkin berkualitas buruk.
    KONTEKS WAKTU: Hari ini tahun {tahun_ini}.
    
    INSTRUKSI & ATURAN KOREKSI (WAJIB DIPATUHI):
    
    1. 🔍 DETEKSI VENDOR (PENTING):
       - Cari nama toko/penjual di bagian paling atas (Kop/Stempel).
       - JANGAN hanya menulis "Toko" atau "Store" jika ada nama spesifik (misal "Toko Sinar Jaya").
       - Jika nama tidak terbaca sama sekali, tulis "TIDAK TERIDENTIFIKASI".
       - Hati-hati membaca logo tulisan sambung.
    
    2. 📅 PERBAIKAN TANGGAL:
       - Jika tahun tertulis singkatan/coretan (misal "17-12-2--" atau "25"), ASUMSIKAN tahun {tahun_ini}.
       - Format wajib: DD-MM-YYYY.
    
    3. 🧮 VALIDASI MATEMATIKA (LOGIC CHECK):
       - Rumus Wajib: (Qty x Harga Satuan) = Total Baris.
       - Jika tulisan Harga sulit dibaca tapi Total jelas, HITUNG MUNDUR: (Total / Qty).
       - Jika Total Invoice tertulis ngawur (salah baca OCR), HITUNG ULANG dari penjumlahan item yang benar.
       - JANGAN PERCAYA MATAMU jika matematikanya salah.
    
    4. 📝 BERSIHKAN DATA:
       - Hapus simbol aneh (misal "_", "|") di nama barang.

    OUTPUT JSON FINAL (HANYA JSON):
    {{
        "tanggal": "DD-MM-YYYY",
        "no_invoice": "String (jika tidak ada tulis '-')",
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
        "catatan_audit": "Jelaskan perbaikan yang kamu lakukan (misal: 'Mengoreksi tahun jadi {tahun_ini}', 'Menghitung ulang harga satuan')"
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
            temperature=0.1, # Rendah agar konsisten
            max_tokens=1024
        )
        content = response.choices[0].message.content
        
        # Pembersihan Markdown JSON
        if "```json" in content: content = content.split("```json")[1].split("```")[0]
        elif "```" in content: content = content.split("```")[1].split("```")[0]
        
        data = json.loads(content)
        data['nama_file_asli'] = image_file.name 
        return data
        
    except Exception as e:
        return {"nama_file_asli": image_file.name, "catatan_audit": f"ERROR SISTEM: {str(e)}"}

# --- 4. UI UTAMA (INTERFACE) ---
st.title("🕵️‍♂️ Invoice Auditor Pro (v3.0)")
st.caption("Batch Processing • Auto-Math Check • Grand Total • One-Click Copy")

# Upload Area
uploaded_files = st.file_uploader(
    "Drop banyak invoice di sini (JPG/PNG)", 
    type=["jpg", "jpeg", "png"], 
    accept_multiple_files=True
)

if uploaded_files:
    jumlah_file = len(uploaded_files)
    st.info(f"📂 {jumlah_file} dokumen terdeteksi.")
    
    if st.button(f"🚀 Audit {jumlah_file} Invoice Sekarang", type="primary"):
        
        all_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # --- PROSES LOOPING ---
        for i, file in enumerate(uploaded_files):
            status_text.text(f"⏳ Sedang mengaudit file {i+1} dari {jumlah_file}: {file.name}...")
            
            # Panggil AI
            hasil = process_single_invoice(file, NVIDIA_API_KEY)
            
            # Flatten JSON ke Format Tabel Excel
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
                        "Catatan Audit": hasil.get('catatan_audit', ''),
                        "Nama File": hasil.get('nama_file_asli', '')
                    }
                    all_results.append(row)
            else:
                # Jika gagal baca item, tetap masukkan data header
                row_error = {
                    "Tanggal": hasil.get('tanggal', ''),
                    "Vendor": hasil.get('vendor', ''),
                    "Catatan Audit": hasil.get('catatan_audit', 'Gagal membaca item'),
                    "Nama File": hasil.get('nama_file_asli', ''),
                    "Total Baris": 0
                }
                all_results.append(row_error)
            
            progress_bar.progress((i + 1) / jumlah_file)
            
        status_text.success("✅ Audit Selesai!")
        time.sleep(1)
        progress_bar.empty()
        
        # --- TAMPILAN HASIL ---
        if all_results:
            df = pd.DataFrame(all_results)
            
            # Pastikan kolom angka benar-benar angka
            df['Total Baris'] = pd.to_numeric(df['Total Baris'], errors='coerce').fillna(0)
            
            # --- FITUR GRAND TOTAL ---
            total_semua = df['Total Baris'].sum()
            
            # Baris Grand Total
            grand_total_row = {k: '' for k in df.columns}
            grand_total_row['Nama Barang'] = '🟣 GRAND TOTAL'
            grand_total_row['Total Baris'] = total_semua
            
            # Gabung untuk display
            df_display = pd.concat([df, pd.DataFrame([grand_total_row])], ignore_index=True)
            
            st.markdown("### 📝 Tabel Hasil & Koreksi")
            # Tampilkan editor
            edited_df = st.data_editor(
                df_display,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Total Baris": st.column_config.NumberColumn(format="Rp %d"),
                    "Harga Satuan": st.column_config.NumberColumn(format="Rp %d"),
                }
            )
            
            st.divider()
            
            # Kolom Layout untuk Tombol
            c1, c2 = st.columns([1, 1])
            
            with c1:
                st.markdown("### 📋 Copy Data (Quick Paste)")
                st.caption("Klik tombol kecil 📄 di pojok kanan kotak hitam ini -> Paste di Excel.")
                # Konversi ke TSV (Tab Separated) agar kolom Excel rapi
                tsv_data = edited_df.to_csv(index=False, sep='\t')
                st.code(tsv_data, language='text')

            with c2:
                st.markdown("### 📥 Download File")
                st.caption("Unduh file Excel rapi untuk arsip.")
                
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    edited_df.to_excel(writer, index=False, sheet_name='AuditData')
                    
                    # Formatting Otomatis Lebar Kolom Excel
                    worksheet = writer.sheets['AuditData']
                    for idx, col in enumerate(edited_df.columns):
                        series = edited_df[col]
                        # Hitung panjang maksimum teks di kolom tsb
                        max_len = max((series.astype(str).map(len).max(), len(str(col)))) + 2
                        worksheet.set_column(idx, idx, max_len)
                
                st.download_button(
                    label="📄 Download Excel (.xlsx)",
                    data=buffer.getvalue(),
                    file_name=f"Rekap_Invoice_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.ms-excel",
                    type="primary",
                    use_container_width=True
                )
