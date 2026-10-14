# Workflow: Requirement Change

**Slash Command:** `/requirement-change`  
**Deskripsi:** Prosedur formal untuk mengevaluasi, menganalisis dampak, dan mengintegrasikan perubahan kebutuhan (*change request*) dari pemangku kepentingan ke seluruh rantai dokumen spesifikasi, arsitektur, dan backlog tugas secara konsisten.

---

## 1. Inputs
- Deskripsi usulan perubahan kebutuhan dari Product Owner atau Business Sponsor.
- Dokumen acuan hirarki: `01-BRD.md > 02-PRD.md > 03-SRD.md > 04-DRD.md > BPMN`.
- Dokumen spesifikasi aktif: `docs/specs/00-analysis.md`, `docs/specs/system-design.md`, `docs/specs/tasks.md`.

## 2. Outputs
- Matriks Analisis Dampak Perubahan (*Change Impact Analysis*).
- Pembaruan versi katalog kebutuhan pada `docs/specs/00-analysis.md`.
- Pembaruan kontrak arsitektur/API pada `docs/specs/system-design.md` beserta entri ADR (Architecture Decision Record).
- Penyesuaian, penambahan, atau pembatalan tugas pada `docs/specs/tasks.md`.

---

## 3. Langkah-Langkah Eksekusi (Numbered Steps)

1. **Uji Validasi Hirarki Sumber Kebenaran (Hierarchy Impact)**  
   - Periksa apakah perubahan diajukan pada level Bisnis (BRD), Produk (PRD), atau Teknis (SRD).
   - Patuhi hirarki: BRD > PRD > SRD > DRD > BPMN. Perubahan teknis TIDAK BOLEH membatalkan intent bisnis tanpa persetujuan Sponsor.
   - Periksa apakah usulan melanggar Segregation of Duties (`BR-002`) atau membuka akses data lintas klien (`BR-014`). Jika melanggar, TOLAK usulan.

2. **Analisis Dampak Hulu-ke-Hilir (Traceability Impact Analysis)**  
   - Identifikasi Requirement ID yang terdampak (`BR-xxx`, `PR-xxx`, `SR-xxx`, `DR-xxx`, `PF-xxx`).
   - Identifikasi skema database (tabel/kolom) yang terpengaruh di `03-SRD.md`.
   - Identifikasi endpoint API dan state transition dokumen yang perlu disesuaikan.
   - Identifikasi skenario UAT yang terpengaruh (apakah mengubah ekspektasi UAT-1 s.d. UAT-8).

3. **Pembaruan Dokumen Analisis Kebutuhan (`00-analysis.md`)**  
   - Tambahkan ID kebutuhan baru atau tandai revisi pada requirement catalog.
   - Catat alasan perubahan dan resolusinya pada *Conflicts & Gaps Register*.

4. **Pembaruan Desain Sistem & ADR (`system-design.md`)**  
   - Perbarui diagram komponen, alur sekuens, ERD, atau kontrak API yang relevan.
   - Catat keputusan perubahan pada bagian Key Decisions Log (format ADR: Konteks, Pilihan, Keputusan, Konsekuensi).

5. **Penyesuaian Task Tracker (`tasks.md`)**  
   - Tambahkan task baru (`T-xxx`) untuk pengerjaan perubahan atau modifikasi task yang belum dikerjakan.
   - Jika ada task yang menjadi usang, tandai statusnya sebagai `[CAN] Canceled` beserta alasan, jangan menghapus baris untuk menjaga audit historis.
   - Perbarui coverage table di bagian bawah `tasks.md`.

6. **Komunikasi Perubahan & Pembaruan Changelog**  
   - Catat rincian perubahan pada `CHANGELOG.md` di bawah bagian `[Changed]`.

---

## 4. Kondisi Berhenti (Stop Conditions)
Agent MUST menghentikan eksekusi workflow dan meminta keputusan manusia jika:
- Perubahan meminta penghapusan pemeriksaan Segregation of Duties.
- Perubahan meminta penghapusan keabadian log audit (*tamper-proof*).
- Perubahan merusak salah satu dari 8 skenario demo penerimaan utama pada Demo Day.
