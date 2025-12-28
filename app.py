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
            "metode_bayar": "string",
            "catatan": "string"
        },
        "items": [
            {
                "deskripsi": "nama barang",
                "qty": integer,
                "satuan": "string",
                "harga_satuan": integer,
                "subtotal": integer
            }
        ]
    }
    
    ATURAN:
    1. Jika data tidak ada, isi null/kosong.
    2. Harga dan angka harus integer murni (tanpa Rp, tanpa titik).
    3. Pastikan list 'items' menangkap SEMUA baris barang.
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
            max_tokens=2048
        )
        content = response.choices[0].message.content
        
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
             content = content.split("```")[1].split("```")[0]
             
        data_raw = json.loads(content)
        
        extracted_rows = []
        header = data_raw.get('header', {})
        items = data_raw.get('items', [])
        
        tgl_input = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        nama_file = image_file.name
        
        if not items:
            items = [{"deskripsi": "Gagal baca detail item", "qty": 0, "satuan": "-", "harga_satuan": 0, "subtotal": 0}]

        for item in items:
            row = {
                "Tanggal Input": tgl_input,             
                "Tanggal Invoice": header.get("tanggal_invoice", "-"), 
                "No Invoice": header.get("no_invoice", "-"),       
                "Vendor/Supplier": header.get("vendor_nama", "-"), 
                "Alamat Vendor": header.get("vendor_alamat", "-"), 
                "No Telp Vendor": header.get("vendor_telp", "-"),  
                "Nama Pembeli": header.get("pembeli_nama", "-"),   
                "Alamat Pembeli": header.get("pembeli_alamat", "-"), 
                "Deskripsi Item": item.get("deskripsi", "-"),      
                "Quantity": item.get("qty", 0),                    
                "Satuan": item.get("satuan", "-"),                 
                "Harga Satuan": item.get("harga_satuan", 0),       
                "Subtotal": item.get("subtotal", 0),               
                "Diskon": header.get("diskon_global", 0),          
                "Pajak/PPN": header.get("pajak_global", 0),        
                "Total": header.get("total_akhir", 0),             
                "Metode Pembayaran": header.get("metode_bayar", "-"), 
                "Status": "Draft",                                 
                "Catatan": header.get("catatan", "-"),             
                "Nama File": nama_file                             
            }
            extracted_rows.append(row)
            
        return extracted_rows
        
    except Exception as e:
        return [{
            "Tanggal Input": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Deskripsi Item": f"ERROR: {str(e)}",
            "Nama File": image_file.name
        }]

# --- 4. UI UTAMA ---
st.title("🏢 Batch Invoice Processor")
st.caption("Mode: Detail Item + Grand Total (Total Only)")

uploaded_files = st.file_uploader(
    "Drop file invoice di sini (JPG/PNG)", 
    type=["jpg", "jpeg", "png"], 
    accept_multiple_files=True
)

if uploaded_files:
    jumlah_file = len(uploaded_files)
    st.info(f"📂 {jumlah_file} file siap diproses.")
    
    if st.button(f"🚀 Proses {jumlah_file} File", type="primary"):
        
        all_rows_flat = [] 
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, file in enumerate(uploaded_files):
            status_text.text(f"⏳ Mengolah: {file.name}...")
            rows = process_single_invoice(file, NVIDIA_API_KEY)
            all_rows_flat.extend(rows)
            progress_bar.progress((i + 1) / jumlah_file)
            
        status_text.empty()
        progress_bar.empty()
        
        if all_rows_flat:
            st.success("✅ Selesai.")
            
            df = pd.DataFrame(all_rows_flat)
            
            # --- CALCULATE GRAND TOTAL (HANYA KOLOM TOTAL) ---
            
            # 1. Konversi semua kolom angka jadi numeric dulu (supaya Excel bisa baca sebagai angka)
            numeric_cols = ["Quantity", "Harga Satuan", "Subtotal", "Diskon", "Pajak/PPN", "Total"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # 2. Buat Baris Grand Total
            total_row = {col: "" for col in df.columns} # Semua kolom kosong dulu
            total_row["Deskripsi Item"] = "GRAND TOTAL" # Label Penanda
            
            # 3. HANYA MENJUMLAHKAN KOLOM 'Total' (Sesuai Request Don)
            if "Total" in df.columns:
                total_row["Total"] = df["Total"].sum()
            
            # 4. Gabungkan ke DataFrame
            df_total = pd.DataFrame([total_row])
            df = pd.concat([df, df_total], ignore_index=True)

            # --- FINAL FORMATTING ---
            final_columns = [
                "Tanggal Input", "Tanggal Invoice", "No Invoice", 
                "Vendor/Supplier", "Alamat Vendor", "No Telp Vendor",
                "Nama Pembeli", "Alamat Pembeli", "Deskripsi Item",
                "Quantity", "Satuan", "Harga Satuan", "Subtotal",
                "Diskon", "Pajak/PPN", "Total", "Metode Pembayaran",
                "Status", "Catatan", "Nama File"
            ]
            
            # Pastikan kolom lengkap
            for col in final_columns:
                if col not in df.columns:
                    df[col] = "-"
            
            # Reorder
            df_final = df[final_columns]
            
            # Tampilkan Tabel
            st.write("### 📝 Hasil Ekstraksi & Grand Total")
            edited_df = st.data_editor(df_final, num_rows="dynamic", use_container_width=True)
            
            st.divider()
            col_action1, col_action2 = st.columns(2)
            
            # DOWNLOAD BUTTON
            with col_action1:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    edited_df.to_excel(writer, index=False, sheet_name='Invoice_Detail')
                    worksheet = writer.sheets['Invoice_Detail']
                    for idx, col in enumerate(edited_df.columns):
                        series = edited_df[col]
                        max_len = max((series.astype(str).map(len).max(), len(str(col)))) + 2
                        worksheet.set_column(idx, idx, max_len)

                st.download_button(
                    label="📥 Download Excel (.xlsx)",
                    data=buffer.getvalue(),
                    file_name=f"Invoice_Total_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.ms-excel",
                    type="primary",
                    use_container_width=True
                )
            
            # COPY BUTTON
            with col_action2:
                tsv_data = edited_df.to_csv(sep='\t', index=False)
                st.markdown("📋 **Salin ke Clipboard:**")
                st.caption("Klik tombol Copy di kanan atas kotak ini -> Paste di Sheets.")
                st.code(tsv_data, language="text")
