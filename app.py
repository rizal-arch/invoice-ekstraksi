import streamlit as st
import pandas as pd
from openai import OpenAI
import base64
import json
import io
import time

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Invoice Extractor Pro (Batch)", page_icon="🏢", layout="wide")

# --- 2. SECURITY & KONFIGURASI SISTEM ---
# Mengambil API Key dari "Brankas" (Secrets)
# Nanti kita set di dashboard Streamlit, bukan di kodingan
try:
    NVIDIA_API_KEY = st.secrets["NVIDIA_API_KEY"]
except:
    st.error("⚠️ API Key belum dipasang di Secrets. Harap hubungi Administrator (Don).")
    st.stop()

# --- 3. LOGIKA MONETISASI (STRUKTUR SAJA) ---
def check_user_quota(user_id, jumlah_upload):
    """
    Fungsi ini adalah 'Penjaga Gerbang'.
    Nanti di sini kita sambungkan ke Database untuk cek:
    Apakah user ini Free? Sisa kuota berapa?
    """
    # UNTUK TAHAP TEST: Kita loloskan semua (return True)
    # Nanti logika '3 Gratis' dipasang di sini.
    return True 

# --- 4. FUNGSI AI (PROCESSOR) ---
def process_single_invoice(image_file, api_key):
    # Encode gambar
    image_bytes = image_file.getvalue()
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

    prompt = """
    Kamu adalah mesin ekstraksi data invoice bulk.
    Tugas: Ekstrak data dari gambar ini ke JSON.
    
    Field Wajib:
    - 'tanggal': (DD-MM-YYYY)
    - 'no_invoice': (string)
    - 'vendor': (nama penjual)
    - 'pembeli': (nama pembeli)
    - 'total_tagihan': (angka/integer dari total akhir)
    - 'list_item': (gabungkan semua nama item jadi satu string dipisah koma jika banyak)
    
    ATURAN:
    Hanya output JSON valid. Tanpa markdown.
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
        
        # Pembersihan String JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
             content = content.split("```")[1].split("```")[0]
             
        data = json.loads(content)
        # Tambahkan nama file asli agar user mudah tracking
        data['nama_file_asli'] = image_file.name 
        return data
        
    except Exception as e:
        return {"nama_file_asli": image_file.name, "error": str(e)}

# --- 5. TAMPILAN ANTARMUKA (UI) ---
st.title("🏢 Batch Invoice Processor")
st.caption("Drop 10, 20, atau 50 file sekaligus. Sistem akan merapikannya menjadi satu Excel.")

# Area Upload Drag & Drop (Batch Enabled)
uploaded_files = st.file_uploader(
    "Seret & Lepas (Drag & Drop) banyak file di sini", 
    type=["jpg", "jpeg", "png"], 
    accept_multiple_files=True  # <--- INI KUNCI BATCH-NYA
)

if uploaded_files:
    jumlah_file = len(uploaded_files)
    st.info(f"📂 {jumlah_file} file terdeteksi.")
    
    if st.button(f"🚀 Proses {jumlah_file} Invoice Sekarang", type="primary"):
        
        # 1. Cek Kuota (Placeholder Monetisasi)
        if not check_user_quota("user_tamu", jumlah_file):
            st.warning("Kuota habis! Upgrade ke Premium untuk batch processing.")
            st.stop()
            
        # 2. Persiapan Wadah Data
        all_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 3. Looping Processing
        for i, file in enumerate(uploaded_files):
            status_text.text(f"⏳ Sedang membaca file {i+1} dari {jumlah_file}: {file.name}...")
            
            # Panggil AI
            hasil = process_single_invoice(file, NVIDIA_API_KEY)
            all_results.append(hasil)
            
            # Update Progress Bar
            progress_bar.progress((i + 1) / jumlah_file)
            
        status_text.text("✅ Selesai! Semua file berhasil dibaca.")
        time.sleep(1)
        status_text.empty()
        progress_bar.empty()
        
        # 4. Tampilkan & Download Hasil
        if all_results:
            st.success("🎉 Ekstraksi Batch Selesai.")
            
            df = pd.DataFrame(all_results)
            
            # Pindah kolom 'nama_file_asli' ke depan biar rapi
            cols = ['nama_file_asli'] + [c for c in df.columns if c != 'nama_file_asli']
            df = df[cols]
            
            # Editable Table
            edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
            
            # Download Logic
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                edited_df.to_excel(writer, index=False, sheet_name='BatchData')
                
            st.download_button(
                label="📥 Download Rekapan Excel (.xlsx)",
                data=buffer.getvalue(),
                file_name="Rekapan_Invoice_Batch.xlsx",
                mime="application/vnd.ms-excel",
                type="primary"
            )
