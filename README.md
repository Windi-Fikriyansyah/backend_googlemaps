# Google Maps Lead Finder - Panduan Jalankan

Aplikasi ini terdiri dari **Backend (FastAPI)** dan **Frontend (Next.js 14)**.

## Persiapan
1. Pastikan Anda memiliki **PostgreSQL** yang sedang berjalan.
2. Pastikan Anda memiliki **Google Maps API Key** (dengan Places API & Geocoding API aktif).

## 1. Menjalankan Backend (Python FastAPI)

1. Buka terminal di folder root (`d:/maps`).
2. Buat Virtual Environment (opsional tapi disarankan):
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Install dependensi:
   ```bash
   pip install -r requirements.txt
   ```
4. Konfigurasi file `.env`:
   - Buka file `.env`.
   - Masukkan `DATABASE_URL` (sesuaikan user/password/db name).
   - Masukkan `GOOGLE_MAPS_API_KEY`.
5. Jalankan server:
   ```bash
   uvicorn main:app --reload
   ```
   Backend akan berjalan di `http://localhost:8000`.

## 2. Menjalankan Frontend (Next.js)

1. Buka terminal baru di folder `d:/maps/frontend`.
2. Install dependensi (jika belum):
   ```bash
   npm install
   ```
3. Jalankan aplikasi:
   ```bash
   npm run dev
   ```
4. Buka browser di `http://localhost:3000`.

## Catatan Penting
- **Database**: Jika tabel belum ada, FastAPI akan otomatis membuatnya saat pertama kali dijalankan (`Base.metadata.create_all`).
- **Google API**: Pastikan kuota API Anda mencukupi karena pencarian mendalam (deep search) akan memanggil Detail API untuk setiap lead.
- **Export**: Data dapat langsung diunduh dalam format CSV melalui tombol di tabel hasil.
