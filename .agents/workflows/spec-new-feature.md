# Workflow: Spec New Feature

**Slash Command:** `/spec-new-feature`  
**Deskripsi:** Prosedur terstruktur untuk mendefinisikan spesifikasi fitur baru dari permintaan bisnis ke dalam arsitektur sistem, katalog requirement ber-ID stabil, dan rincian task tracker tanpa menimbulkan celah atau kontradiksi spesifikasi.

---

## 1. Inputs
- Deskripsi fitur baru atau user story dari Product Owner / User.
- Dokumen acuan sumber kebenaran: `01-BRD.md`, `02-PRD.md`, `03-SRD.md`, `04-DRD.md`, `AMIGA_Robot_Admin_Invoice_to_Voucher ver3.bpmn`.
- Dokumen spesifikasi aktif: `docs/specs/00-analysis.md` dan `docs/specs/system-design.md`.

## 2. Outputs
- Entri requirement baru dengan ID stabil (`BR-xxx`, `PR-xxx`, `SR-xxx`, `DR-xxx`) pada `docs/specs/00-analysis.md`.
- Pembaruan spesifikasi arsitektur / API contract / skema data pada `docs/specs/system-design.md`.
- Rincian tugas baru ber-ID `T-xxx` pada `docs/specs/tasks.md` lengkap dengan Acceptance Criteria (Given-When-Then).

---

## 3. Langkah-Langkah Eksekusi (Numbered Steps)

1. **Uji Keselarasan Visi & Segregation of Duties (SoD)**  
   Periksa apakah fitur baru melanggar kontrol inti:
   - Apakah fitur mengizinkan pengunggah menyetujui dokumen sendiri? Jika ya, REJECT fitur atau ubah agar mematuhi aturan SoD (`BR-002`, `SR-004`).
   - Apakah fitur berada di luar cakupan sistem (misal eksekusi pembayaran internet banking)? Jika ya, tandai sebagai Non-Goals (`00-product-context.md`).

2. **Penetapan ID Kebutuhan Stabil (Requirement ID Tagging)**  
   Tetapkan ID unik berurutan:
   - Kebutuhan bisnis: `BR-xxx`
   - Kebutuhan produk/fungsional: `PR-xxx`
   - Kebutuhan teknis/sistem: `SR-xxx`
   - Kebutuhan desain/antarmuka: `DR-xxx`

3. **Pemetaan Alur BPMN & Model Data**  
   - Periksa apakah fitur memodifikasi 6 status resmi dokumen (`QUEUED`, `PROCESSING`, `READY_FOR_REVIEW`, `EXCEPTION`, `AMIGA_REVIEWED`, `SENT_TO_CLIENT`).
   - Jika membutuhkan tabel/kolom baru, definisikan field, tipe, constraint, dan relasi yang selaras dengan 10 entitas di `03-SRD.md`.

4. **Perumusan Kontrak API & Layar Antarmuka**  
   - Definisikan method, endpoint, auth role, payload request, envelope response, dan error code RFC 7807.
   - Petakan antarmuka ke salah satu dari 5 layar utama dengan token desain *"Navy Ink on Cool Marble"*.

5. **Penyusunan Rincian Tugas di `docs/specs/tasks.md`**  
   Pecah fitur menjadi tugas-tugas kecil (estimasi <= setengah hari per task) memuat:
   - ID Tugas (`T-xxx`), Judul, Deskripsi.
   - Requirement IDs yang dipenuhi.
   - Acceptance Criteria teruji (Given-When-Then).
   - Pengujian wajib (Unit / Integration / E2E).
   - Estimasi (S/M/L) dan berkas yang disentuh.

6. **Self-Review Terhadap Aturan Anti-Slop**  
   Pastikan tidak ada teks em dash (`—`), tidak ada tombol pill generic tanpa alasan, dan tidak ada klaim performa tanpa metrik pengujian nyata.

---

## 4. Kondisi Berhenti (Stop Conditions)
Agent MUST menghentikan eksekusi workflow dan meminta konfirmasi jika:
- Fitur memerlukan perubahan mendasar pada 6 siklus status dokumen yang telah disahkan BPMN.
- Terdapat kontradiksi langsung terhadap integritas `audit_logs` (misal permintaan menghapus riwayat log).
- Pemilik bisnis belum menentukan prioritas (P0 atau P1) untuk fitur tersebut.
