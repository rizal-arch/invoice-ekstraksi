import streamlit as st
import pandas as pd
from openai import OpenAI
import base64
import json
import io
import time
from datetime import datetime

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Invoice Extractor Pro", page_icon="🏢", layout="wide")

# --- 2. SECURITY ---
try:
    NVIDIA_API_KEY = st.secrets["NVIDIA_API_KEY"]
except:
    st.error("⚠️ API Key belum dipasang di Secrets.")
    st.stop()

# --- 3. FUNGSI AI (PROCESSOR) ---
def process_single_invoice(image_file, api_key):
    # Encode gambar
    image_bytes = image_file.getvalue()
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

    # PROMPT KHUSUS: ITEM-LEVEL EXTRACTION
    prompt = """
    Kamu adalah sistem entri data invoice detail.
    Tugas: Ekstrak data HEADER dan DATA ITEM (baris per baris) dari gambar invoice ini.
    
    OUTPUT WAJIB JSON dengan struktur berikut:
    {
        "header": {
            "tanggal_invoice": "DD-MM-YYYY",
            "no_invoice": "string",
            "vendor_nama": "string",
            "vendor_alamat": "string",
            "vendor_telp": "string",
            "pembeli_nama": "string",
            "pembeli_alamat": "string",
            "diskon_global": integer,
            "pajak_global": integer,
            "total_akhir": integer,
            "metode_bayar": "string (Cash/Transfer/Credit)",
            "catatan": "string"
        },
        "items": [
            {
                "deskripsi": "nama barang",
                "qty": integer,
                "satuan": "string (pcs/kg/box/unit)",
                "harga_satuan": integer,
                "subtotal": integer
            }
        ]
    }
    
    ATURAN:
    1. Jika data (alamat/telp/dll) tidak ada di gambar, isi dengan null atau string kosong "".
    2. Harga dan angka harus integer murni (tanpa Rp, tanpa titik/koma).
    3. Pastikan list 'items' menangkap SEMUA baris barang yang ada.
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
            max_tokens=2048 # Token diperbesar karena output JSON lebih panjang
        )
        content = response.choices[0].message.content
        
        # Bersihkan Markdown JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
             content = content.split("```")[1].split("```")[0]
             
        data_raw = json.loads(content)
        
        # --- LOGIKA FLATTENING (MEMECAH MENJADI BARIS PER ITEM) ---
        extracted_rows = []
        header = data_raw.get('header', {})
        items = data_raw.get('items', [])
        
        # Metadata standar
        tgl_input = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        nama_file = image_file.name
        
        # Jika AI gagal baca items atau item kosong, buat 1 baris dummy agar invoice tetap tercatat
        if not items:
            items = [{"deskripsi": "Gagal baca detail item", "qty": 0, "satuan": "-", "harga_satuan": 0, "subtotal": 0}]

        for item in items:
            # Kita gabungkan data Header + Data Item menjadi satu baris flat
            row = {
                "Tanggal Input": tgl_input,             # A
                "Tanggal Invoice": header.get("tanggal_invoice", "-"), # B
                "No Invoice": header.get("no_invoice", "-"),       # C
                "Vendor/Supplier": header.get("vendor_nama", "-"), # D
                "Alamat Vendor": header.get("vendor_alamat", "-"), # E
                "No Telp Vendor": header.get("vendor_telp", "-"),  # F
                "Nama Pembeli": header.get("pembeli_nama", "-"),   # G
                "Alamat Pembeli": header.get("pembeli_alamat", "-"), # H
                
                # Data Item Spesifik
                "Deskripsi Item": item.get("deskripsi", "-"),      # I
                "Quantity": item.get("qty", 0),                    # J
                "Satuan": item.get("satuan", "-"),                 # K
                "Harga Satuan": item.get("harga_satuan", 0),       # L
                "Subtotal": item.get("subtotal", 0),               # M
                
                # Data Keuangan Lain
                "Diskon": header.get("diskon_global", 0),          # N (Note: Biasanya diskon per invoice, bukan per item, tapi kita taruh di tiap baris)
                "Pajak/PPN": header.get("pajak_global", 0),        # O
                "Total": header.get("total_akhir", 0),             # P
                "Metode Pembayaran": header.get("metode_bayar", "-"), # Q
                "Status": "Draft",                                 # R (Default status)
                "Catatan": header.get("catatan", "-"),             # S
                "Nama File": nama_file                             # T
            }
            extracted_rows.append(row)
            
        return extracted_rows
        
    except Exception as e:
        # Return baris error agar user tahu file mana yang gagal
        return [{
            "Tanggal Input": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Deskripsi Item": f"ERROR: {str(e)}",
            "Nama File": image_file.name
        }]

# --- 4. UI UTAMA ---
st.title("🏢 Batch Invoice Processor (Detail Item)")
st.caption("Mode: Satu Baris per Item Barang. Kolom Lengkap A-T.")

uploaded_files = st.file_uploader(
    "Drop file invoice di sini (JPG/PNG)", 
    type=["jpg", "jpeg", "png"], 
    accept_multiple_files=True
)

if uploaded_files:
    jumlah_file = len(uploaded_files)
    st.info(f"📂 {jumlah_file} file siap diproses.")
    
    if st.button(f"🚀 Proses Detail ({jumlah_file} File)", type="primary"):
        
        all_rows_flat = [] # List untuk menampung semua baris dari semua invoice
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Loop Processing
        for i, file in enumerate(uploaded_files):
            status_text.text(f"⏳ Mengolah: {file.name}...")
            
            # AI Process returns LIST of rows (karena 1 invoice bisa banyak item)
            rows = process_single_invoice(file, NVIDIA_API_KEY)
            
            # Extend list utama
            all_rows_flat.extend(rows)
            
            progress_bar.progress((i + 1) / jumlah_file)
            
        status_text.empty()
        progress_bar.empty()
        
        if all_rows_flat:
            st.success("✅ Selesai.")
            
            df = pd.DataFrame(all_rows_flat)
            
            # URUTAN KOLOM FINAL (SESUAI PERMINTAAN DON)
            final_columns = [
                "Tanggal Input", "Tanggal Invoice", "No Invoice", 
                "Vendor/Supplier", "Alamat Vendor", "No Telp Vendor",
                "Nama Pembeli", "Alamat Pembeli", "Deskripsi Item",
                "Quantity", "Satuan", "Harga Satuan", "Subtotal",
                "Diskon", "Pajak/PPN", "Total", "Metode Pembayaran",
                "Status", "Catatan", "Nama File"
            ]
            
            # Pastikan kolom yang belum ada (misal karena error) tetap muncul
            for col in final_columns:
                if col not in df.columns:
                    df[col] = "-"
            
            # Reorder DataFrame
            df_final = df[final_columns]
            
            # Tampilkan Tabel
            st.write("### 📝 Hasil Detail Per Item")
            edited_df = st.data_editor(df_final, num_rows="dynamic", use_container_width=True)
            
            # Download Logic
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                edited_df.to_excel(writer, index=False, sheet_name='Invoice_Detail')
                
                # Auto-fit Column Width
                worksheet = writer.sheets['Invoice_Detail']
                for idx, col in enumerate(edited_df.columns):
                    series = edited_df[col]
                    max_len = max((series.astype(str).map(len).max(), len(str(col)))) + 2
                    worksheet.set_column(idx, idx, max_len)

            st.download_button(
                label="📥 Download Excel Lengkap (.xlsx)",
                data=buffer.getvalue(),
                file_name=f"Invoice_Detail_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.ms-excel",
                type="primary",
                use_container_width=True
            )
