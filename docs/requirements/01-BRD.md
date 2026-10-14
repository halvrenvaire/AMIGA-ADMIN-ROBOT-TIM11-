# **BUSINESS REQUIREMENTS DOCUMENT (BRD)**

**AMIGA Robot Admin — Intelligent Vendor Invoice-to-Voucher Processing**

| Field | Detail |
| :---- | :---- |
| **Versi Dokumen** | v1.1 (Draft — disesuaikan dengan BPMN revisi) |
| **Terakhir Diperbarui** | 13/10/2026 |
| **Product Owner** | Tim AMIGA Intelligent Back Office |
| **Business Sponsor** | MAIN  |
| **Tech Lead / Architect** | TEAM 11 MAIN  |
| **Target Sprint Kick-off** | Selasa, 13 Oktober 2026 |

## 

## **1\. Executive Summary & Problem Framing**

### 

### **1.1 Visi Produk (Product Vision)**

Membangun Produk AMIGA ROBOT ADMIN Menjadi mitra strategis operasional back office pilihan yang unggulan dalam pengelolaan keuangan, perpajakan, SDM, dan administrasi bisnis yang akurat, patuh regulasi, serta terintegrasi. 

### **1.2 Latar Belakang Bisnis**

AMIGA beroperasi sebagai *Back Office Operating Partner* untuk klien multi-industri, mengelola fungsi keuangan, akuntansi, perpajakan, penggajian, SDM dan administrasi bisnis. Saat ini proses pengolahan tagihan vendor masih sepenuhnya manual dan terfragmentasi:

* Data dari berkas fisik/PDF diinput ulang ke lembar kerja *spreadsheet*.  
* Voucher pembayaran dibuat secara manual.  
* Kelengkapan dokumen pendukung diperiksa satu per satu.  
* Komunikasi dan pemantauan status pekerjaan tersebar di WhatsApp dan Email.

### 

### **1.3 Problem Statement (Masalah Utama)**

> 1. **Beban Operasional Manual**: Mengetik ulang data dari invoice yang tidak terstruktur memakan waktu 5–10 menit per invoice, dan penyusunan voucher 5–15 menit. Kapasitas tim terkuras untuk pekerjaan repetitif, dan *throughput* harian dibatasi kecepatan input manual.  
> 2. **Risiko Kesalahan Manusia**: Salah ketik nominal dan nomor rekening bank, salah hitung total invoice, serta potensi pembayaran ganda (*duplicate payment*) pada vendor yang sama.  
> 3. **Visibilitas & Auditabilitas Terbatas**: Riwayat perubahan data sulit ditelusuri, tidak ada jejak persetujuan yang dapat diaudit, dan serah terima antar-PIC tidak transparan sehingga konteks pekerjaan mudah hilang.

### 

### **1.4 Target Audience / User Persona**

* **Primary Persona (PIC Klien & Intake Support)**: Pihak yang mengunggah invoice PDF, mengisi metadata awal, menyelesaikan kendala dokumen, dan mengunduh voucher resmi. Membutuhkan proses unggah yang cepat dan status yang jelas tanpa harus menanyakan lewat WhatsApp/Email.  
* **Primary Persona (Finance Reviewer AMIGA)**: Tim Keuangan yang memeriksa, mengoreksi dan menyetujui hasil ekstraksi. Membutuhkan layar peninjauan yang menampilkan dokumen asli berdampingan dengan data hasil ekstraksi serta indikator validasi.  
* **Secondary Persona (Service Lead & System Admin)**: Service Lead memantau beban kerja dan mengalokasikan ulang tugas; System Admin mengelola akun, hak akses dan pengaturan data klien.

### 

### **1.5 Operating Model & Pembagian Peran (Hybrid Intake)**

Pemisahan tugas (*Segregation of Duties*) adalah kontrol inti: tidak ada satu peran pun yang dapat mengunggah sekaligus menyetujui dokumen yang sama.

| Peran | Tanggung Jawab | Batasan Kontrol |
| :---- | :---- | :---- |
| **PIC Klien (Owner)** | Mengunggah invoice, mengisi metadata, menyelesaikan kendala, mengunduh voucher. | Tidak boleh meninjau dokumen yang diunggah sendiri. |
| **Intake Support / Backup** | Membantu unggah dan *follow-up* berdasarkan delegasi resmi. | Akses terbatas pada klien yang ditugaskan. |
| **Robot Admin (AI Engine)** | Ekstraksi data invoice: membaca PDF dan mengisi draf voucher. | Tidak berwenang menyetujui voucher. |
| **Sistem AMIGA Robot Admin** | Menerbitkan Request ID, memverifikasi angka, kelengkapan dan duplikasi, menandai EXCEPTION, mengecek Segregation of Duties (termasuk menolak dan mengalihkan otomatis ke reviewer lain) dan membuat voucher PDF. | Tidak berwenang menyetujui voucher; hanya menjalankan aturan yang disepakati. |
| **Finance Reviewer** | Memeriksa, mengoreksi dan menyetujui hasil ekstraksi. | Tidak meninjau dokumen yang diunggah sendiri. |
| **Service Lead** | Memantau beban kerja reviewer dan mengalihkan dokumen ke reviewer lain bila beban seorang reviewer terlalu banyak. | Tidak mengotorisasi pembayaran klien. |
| **System Admin** | Mengelola akun, hak akses dan pengaturan data klien. | Tidak memiliki akses persetujuan transaksi. |
| **Client Approver (External)** | Menyetujui dan melakukan pembayaran di luar AMIGA. | Di luar cakupan aplikasi. |

## 

## **2\. Business Goals & Success Metrics (OKRs / KPIs)**

| Kategori | Indikator Metrik (KPI / OKR) | Nilai Saat Ini (Baseline) | Target PoC |
| :---- | :---- | :---- | :---- |
| **Efisiensi** | Waktu ekstraksi data per invoice PDF (hingga 5 halaman) | 5–10 menit input manual per invoice | ≤ 15 detik per dokumen |
| **Efisiensi** | Waktu muat antrean & layar review | Pencarian dokumen fisik & rekap spreadsheet manual | ≤ 2 detik |
| **Efisiensi** | Waktu pembuatan voucher PDF setelah persetujuan reviewer | 5–15 menit penyusunan manual | ≤ 3 detik |
| **Akurasi** | Invoice multi-line item (≥ 3 baris) terbaca lengkap dengan total yang benar | Bergantung ketelitian input manual | 100% baris terbaca & total benar pada skenario uji |
| **Kontrol Risiko** | Invoice duplikat (nomor & vendor sama) yang lolos tanpa ditandai | Tidak ada deteksi sistematis | 0 kasus — 100% ditandai sebagai kemungkinan duplikat |
| **Kepatuhan** | Pelanggaran Segregation of Duties & akses lintas klien | Tidak ada kontrol sistem | 0 kasus — sistem menolak 100% upaya |
| **Audit** | Perubahan data yang tercatat di jejak audit (nilai awal, nilai baru, nama, waktu) | Tidak tercatat | 100% perubahan tercatat |

*Catatan: target efisiensi diambil langsung dari dokumen kebutuhan AMIGA; target akurasi, kontrol risiko, kepatuhan dan auditabilitas diturunkan dari skenario uji penerimaan (Bagian 8).*

## 

## **3\. Agile Scope Boundary (MVP Scoping)**

### **In-Scope (Fokus PoC / Rilis Awal)**

* \[x\] **Intake & Antrean Dokumen**: Unggah invoice PDF beserta metadata awal (klien, jenis permintaan, saluran, tanggal), penerbitan Request ID otomatis dan status QUEUED.  
* \[x\] **AI Extraction**: Pembacaan invoice PDF untuk mengekstrak informasi utama, *line items* dan informasi pembayaran ke dalam draf voucher.  
* \[x\] **Verifikasi Aturan Bisnis oleh Sistem**: Pemeriksaan angka/perhitungan, kelengkapan dokumen (misalnya nomor rekening) dan deteksi duplikasi, dengan hasil READY\_FOR\_REVIEW atau EXCEPTION. Dokumen EXCEPTION ditampilkan beserta kode kendala dan alasannya, lalu diekstraksi dan diverifikasi ulang dengan Request ID yang sama setelah PIC Klien memperbaikinya.  
* \[x\] **Peninjauan Independen (Human Review)**: Layar *split-screen* untuk memeriksa, mengoreksi dan menyetujui hasil ekstraksi oleh Finance Reviewer, atau mengembalikannya ke PIC Klien disertai alasan.  
* \[x\] **Voucher PDF & Handover**: Pratinjau dan unduh voucher PDF resmi lengkap dengan teks batas otorisasi; status SENT\_TO\_CLIENT.  
* \[x\] **Kontrol Akses**: Akses berbasis peran, isolasi data antar-klien dan penegakan Segregation of Duties; persetujuan yang ditolak karena SoD dialihkan otomatis oleh sistem ke reviewer lain.  
* \[x\] **Jejak Audit**: Kronologi aktivitas, catatan penolakan dan riwayat revisi data per dokumen.  
* \[x\] **Dashboard Antrean Kerja**: Ringkasan status, penyaringan per klien, tenggat waktu dan indikasi kendala.

### **Out-of-Scope (Backlog Fase / Iterasi Berikutnya)**

* \[ \] Persetujuan dan eksekusi pembayaran oleh klien (dilakukan Client Approver di luar sistem).  
* \[ \] Portal atau akun untuk Client Approver eksternal.  
* \[ \] Integrasi otomatis ke sistem akuntansi/ERP, *internet banking* atau *payment gateway*.  
* \[ \] Penarikan invoice otomatis dari WhatsApp/Email (saluran hanya dicatat sebagai metadata).  
* \[ \] Format masukan selain PDF (foto, Excel, Word) dan invoice lebih dari 5 halaman.  
* \[ \] Validasi perpajakan lanjutan (misalnya verifikasi Faktur Pajak ke sistem DJP).

### **Alur Kerja To-Be (Proposed Workflow)**

| Tahap | Pelaku | Aktivitas | Status Hasil |
| :---- | :---- | :---- | :---- |
| **1\. Intake** | PIC Klien / Backup | Mengunggah invoice PDF dan melengkapi informasi awal. | — |
| **2\. Queue** | Sistem | Menerbitkan Request ID dan memasukkan dokumen ke antrean. | QUEUED |
| **3\. AI Extraction** | Mesin AI | Membaca isi invoice dan mengisi draf voucher. | PROCESSING |
| **4\. Verification** | Sistem (aturan bisnis) | Memverifikasi angka/perhitungan, kelengkapan dan duplikasi. Bila tidak lolos, menandai EXCEPTION beserta kode kendala dan alasan. | READY\_FOR\_REVIEW (lolos seluruh verifikasi) EXCEPTION (ditemukan kejanggalan) |
| **4a. Perbaikan** | PIC Klien / Backup | Melengkapi atau memperbaiki data invoice. Dokumen kembali ke tahap ekstraksi dengan Request ID yang sama, lalu diverifikasi ulang. | PROCESSING (kembali ke tahap 3\) |
| **5\. Human Review** | Tim Keuangan AMIGA | Meninjau dan mengoreksi data hasil ekstraksi, perhitungan dan kelengkapan dokumen, lalu menyetujui atau mengembalikan ke PIC Klien. | Setujui → tahap 5a; Kembalikan → EXCEPTION (tahap 4a) |
| **5a. Cek SoD** | Sistem | Sistem menolak persetujuan bila penyetuju adalah pengunggah dokumen, lalu otomatis mengalihkan dokumen ke reviewer lain untuk ditinjau ulang (kembali ke tahap 5). | AMIGA\_REVIEWED (bila lolos); voucher PDF dibuat |
| **6\. Client Handover** | PIC Klien | Mengunduh voucher PDF resmi. | SENT\_TO\_CLIENT |
| **7\. External Follow-up** | Client Approver | Persetujuan dan pembayaran dilakukan klien di luar sistem. | — (di luar sistem) |

## 

## **4\. Epic & High-Level User Stories (Backlog Feeder)**

### **Epic 1: Intake & Antrean Dokumen**

* **Story 1.1**: Sebagai PIC Klien, saya ingin mengunggah invoice PDF dan mengisi metadata awal agar tagihan vendor saya masuk ke proses tanpa harus dikirim lewat WhatsApp/Email.  
  * **Business Acceptance Criteria (AC)**:  
    * Formulir menerima file PDF dan wajib mengisi klien, jenis permintaan, saluran dan tanggal.  
    * Setelah unggah berhasil, sistem menerbitkan Request ID unik dan status berubah menjadi QUEUED.  
* **Story 1.2**: Sebagai Intake Support / Backup, saya ingin mengunggah dan menindaklanjuti dokumen atas nama klien yang didelegasikan agar pekerjaan tetap berjalan saat PIC berhalangan.  
  * **Business Acceptance Criteria (AC)**:  
    * Intake Support hanya dapat melihat dan mengunggah dokumen untuk klien yang ditugaskan kepadanya.  
    * Jejak audit mencatat nama pengunggah sebenarnya dan atas nama klien siapa.

### **Epic 2: AI Extraction**

* **Story 2.1**: Sebagai Finance Reviewer, saya ingin AI membaca invoice dan mengisi draf voucher secara otomatis agar saya tidak perlu mengetik ulang data.  
  * **Business Acceptance Criteria (AC)**:  
    * AI mengekstrak informasi utama (vendor, nomor & tanggal invoice), seluruh *line items* dan informasi pembayaran (bank, nomor rekening, nama penerima).  
    * Ekstraksi selesai ≤ 15 detik untuk PDF hingga 5 halaman; selama proses berlangsung status PROCESSING.  
    * Invoice dengan ≥ 3 jenis barang terbaca seluruh barisnya dan totalnya dihitung benar.

### **Epic 3: Verifikasi Aturan Bisnis (oleh Sistem)**

* **Story 3.1**: Sebagai Finance Reviewer, saya ingin sistem memeriksa perhitungan, kelengkapan dan duplikasi secara otomatis agar kejanggalan tertangkap sebelum saya meninjau.  
  * **Business Acceptance Criteria (AC)**:  
    * Invoice tanpa nomor rekening ditandai MISSING\_EVIDENCE dan status menjadi EXCEPTION.  
    * Invoice dengan nomor dan vendor yang sama dengan dokumen sebelumnya ditandai POSSIBLE\_DUPLICATE.  
    * Selisih antara jumlah *line items* dan total invoice ditandai CALCULATION\_DISCREPANCY dan status menjadi EXCEPTION.  
    * Dokumen yang lolos seluruh validasi berstatus READY\_FOR\_REVIEW.  
* **Story 3.2**: Sebagai PIC Klien, saya ingin melihat alasan dokumen berstatus EXCEPTION agar saya dapat melengkapi atau memperbaikinya.  
  * **Business Acceptance Criteria (AC)**:  
    * Setiap EXCEPTION menampilkan kode dan penjelasan kendala yang dapat dipahami pengguna non-teknis.  
    * Setelah PIC Klien melengkapi atau memperbaiki data, dokumen kembali ke tahap ekstraksi dengan Request ID yang sama (tidak diterbitkan Request ID baru), lalu diverifikasi ulang.

### **Epic 4: Peninjauan Independen (Human Review)**

* **Story 4.1**: Sebagai Finance Reviewer, saya ingin melihat PDF asli berdampingan dengan data hasil ekstraksi yang dapat diedit agar verifikasi cepat dan akurat.  
  * **Business Acceptance Criteria (AC)**:  
    * Layar *split-screen*: PDF asli di kiri, data ekstraksi yang dapat diedit di kanan, lengkap dengan indikator hasil validasi.  
    * Layar review termuat ≤ 2 detik.  
    * Persetujuan reviewer yang lolos cek Segregation of Duties mengubah status menjadi AMIGA\_REVIEWED.  
    * Reviewer dapat mengembalikan dokumen ke PIC Klien disertai alasan; status kembali menjadi EXCEPTION.  
* **Story 4.2**: Sebagai Business Sponsor, saya ingin sistem menolak persetujuan oleh pengunggah dokumen yang sama agar tidak terjadi konflik kepentingan.  
  * **Business Acceptance Criteria (AC)**:  
    * Jika User A mengunggah lalu mencoba menyetujui dokumen yang sama, sistem menolak.  
    * Dokumen yang ditolak dialihkan otomatis oleh sistem ke reviewer lain lalu ditinjau ulang; penolakan dan pengalihan tercatat di jejak audit.

### **Epic 5: Voucher PDF & Client Handover**

* **Story 5.1**: Sebagai PIC Klien, saya ingin mengunduh voucher PDF resmi setelah ditinjau agar dapat diteruskan ke Client Approver.  
  * **Business Acceptance Criteria (AC)**:  
    * Voucher PDF terbentuk ≤ 3 detik setelah persetujuan reviewer.  
    * Layar pratinjau menampilkan draf voucher sebelum dicetak/diunduh dengan teks batas otorisasi tetap tercantum.  
    * Setelah voucher diunduh, status berubah menjadi SENT\_TO\_CLIENT.

### **Epic 6: Dashboard Antrean & Manajemen Beban Kerja**

* **Story 6.1**: Sebagai Service Lead, saya ingin melihat ringkasan antrean kerja dan mengalokasikan ulang tugas agar tenggat waktu klien terpenuhi.  
  * **Business Acceptance Criteria (AC)**:  
    * Dashboard menampilkan ringkasan status, penyaringan per klien, tenggat waktu dan indikasi kendala.  
    * Bila beban seorang reviewer terlalu banyak, Service Lead dapat mengalihkan dokumen ke reviewer lain, dan pengalihan tercatat di jejak audit.

### **Epic 7: Keamanan Akses & Isolasi Multi-Klien**

* **Story 7.1**: Sebagai System Admin, saya ingin mengelola akun, peran dan penugasan klien agar setiap pengguna hanya mengakses data yang menjadi haknya.  
  * **Business Acceptance Criteria (AC)**:  
    * User Klien A yang mencoba membuka dokumen Klien B ditolak sepenuhnya.  
    * System Admin tidak memiliki akses untuk menyetujui transaksi.

### **Epic 8: Riwayat & Jejak Audit**

* **Story 8.1**: Sebagai auditor internal/eksternal, saya ingin menelusuri riwayat setiap dokumen dari awal hingga akhir agar setiap keputusan dapat dipertanggungjawabkan.  
  * **Business Acceptance Criteria (AC)**:  
    * Jika reviewer mengubah nominal, sistem mencatat nilai awal, nilai baru, nama reviewer dan waktu perubahan.  
    * Layar riwayat menampilkan kronologi aktivitas, catatan penolakan dan revisi data.

### **Lima Layar Utama Antarmuka**

| Layar | Fungsi Utama | Pengguna Utama |
| :---- | :---- | :---- |
| **01 Dashboard Antrean Kerja** | Ringkasan status, filter per klien, tenggat waktu dan indikasi kendala. | Service Lead, Finance Reviewer |
| **02 Pengunggahan Dokumen** | Unggah PDF invoice dan isi metadata awal (klien, jenis permintaan, saluran, tanggal). | PIC Klien, Intake Support |
| **03 Peninjauan & Verifikasi** | Split-screen PDF asli dan data ekstraksi yang dapat diedit, dengan indikator validasi. | Finance Reviewer |
| **04 Pratinjau Voucher** | Draf voucher PDF sebelum dicetak/diunduh, dengan teks batas otorisasi. | Finance Reviewer, PIC Klien |
| **05 Riwayat & Jejak Audit** | Kronologi aktivitas, catatan penolakan dan revisi data dari awal hingga akhir. | Semua peran sesuai hak akses |

## 

## **5\. Non-Functional Requirements (NFRs)**

* **Performance**: Ekstraksi AI ≤ 15 detik per PDF (hingga 5 halaman); pemuatan antrean dan layar review ≤ 2 detik; pembuatan voucher PDF ≤ 3 detik setelah persetujuan.  
* **Security & Access Control**:  
  * Kontrol akses berbasis peran sesuai Operating Model (Bagian 1.5), ditegakkan di sisi server, bukan hanya di tampilan.  
  * Isolasi data antar-klien: pengguna hanya dapat mengakses dokumen klien yang ditugaskan.  
  * Segregation of Duties: pengunggah dokumen tidak dapat meninjau atau menyetujui dokumen yang sama.  
  * Enkripsi data saat transmisi (TLS) dan saat disimpan, karena dokumen memuat data rekening bank.  
* **Compliance & Data Privacy**: Pengelolaan data pribadi dan data rekening mematuhi UU Perlindungan Data Pribadi (UU PDP); data invoice yang dikirim ke layanan AI pihak ketiga tidak boleh digunakan untuk pelatihan model.  
* **Auditability**: Jejak audit bersifat permanen dan tidak dapat diubah atau dihapus oleh peran mana pun, termasuk System Admin.  
* **Usability**: Setiap layar dirancang untuk peran dan alur kerja spesifik, bukan dashboard serbaguna; pesan kendala menggunakan bahasa yang dipahami pengguna non-teknis.  
* **Reliability**: Kegagalan ekstraksi AI tidak menghilangkan dokumen — dokumen tetap tersimpan dan dapat diproses ulang atau diinput manual oleh reviewer.

## 

## **6\. Assumptions, Dependencies & Risks**

### **6.1 Asumsi Bisnis & Operasional**

* Invoice vendor yang diproses berformat PDF digital dengan maksimal 5 halaman.  
* Peninjauan independen oleh tim Keuangan AMIGA tetap wajib untuk setiap dokumen; AI hanya membantu, tidak menggantikan persetujuan.  
* Persetujuan dan pembayaran tetap dilakukan Client Approver di luar sistem AMIGA.  
* Data uji (contoh invoice dan data klien) untuk PoC menggunakan data dummy atau data yang telah dianonimkan.

### **6.2 Dependensi Eksternal & Internal**

* Ketersediaan layanan AI/OCR untuk ekstraksi dokumen beserta kuota dan kebijakan privasi datanya.  
* Format voucher standar AMIGA (template, teks batas otorisasi, penomoran) dari tim Keuangan.  
* Daftar aturan validasi bisnis dan definisi kode kendala yang disepakati dengan tim Keuangan AMIGA.  
* Daftar peran pengguna, klien dan penugasan untuk konfigurasi hak akses.

### **6.3 Matriks Risiko & Rencana Mitigasi**

| Identifikasi Risiko | Tingkat | Rencana Mitigasi |
| :---- | :---- | :---- |
| **Akurasi ekstraksi AI rendah pada layout invoice yang beragam atau hasil pindaian buruk** | High | Peninjauan manusia wajib sebelum voucher terbit. Tampilkan indikator validasi dan tandai field yang perlu dicek. |
| **Kebocoran data antar-klien atau data rekening bank** | High | Isolasi data per klien yang ditegakkan di server. Enkripsi data dan pengujian akses lintas klien (Skenario 6). |
| **Duplikasi pembayaran tidak terdeteksi (nomor invoice ditulis berbeda)** | Medium | Normalisasi nomor invoice dan nama vendor sebelum dibandingkan. Kombinasikan dengan pemeriksaan nominal dan tanggal. |
| **Pengguna tetap memakai WhatsApp/Email karena kebiasaan** | Medium | Status dokumen transparan di dashboard sehingga pengguna tidak perlu bertanya. Catat saluran asal sebagai metadata untuk transisi bertahap. |
| **Data invoice terpapar ke penyedia AI pihak ketiga** | Medium | Gunakan layanan dengan kebijakan *no-training* dan data dummy untuk PoC. |

## 

## **7\. Delivery Roadmap & Sprint Milestones**

\[Sprint 0: Setup, Desain UI 5 Layar & Model Data\]  
│  
▼  
\[Sprint 1: Intake, Antrean & AI Extraction\]  
│  
▼  
\[Sprint 2: Validasi Aturan Bisnis & Layar Review Split-Screen\]  
│  
▼  
\[Sprint 3: Voucher PDF, Hak Akses/SoD & Jejak Audit\]  
│  
▼  
\[UAT 8 Skenario Penerimaan\] ──► \[Demo Day MAIN Hackathon 2026\]

* **Sprint 0**: Finalisasi alur kerja dan status dokumen, desain UI lima layar utama, model data, serta pemilihan layanan AI.  
* **Sprint 1**: Formulir unggah dan metadata, penerbitan Request ID, antrean (QUEUED → PROCESSING), dan ekstraksi AI untuk informasi utama, *line items* dan pembayaran.  
* **Sprint 2**: Aturan validasi (perhitungan, kelengkapan, duplikasi), status READY\_FOR\_REVIEW/EXCEPTION, dan layar review *split-screen* dengan edit data.  
* **Sprint 3**: Pratinjau dan pembuatan voucher PDF, status AMIGA\_REVIEWED → SENT\_TO\_CLIENT, hak akses berbasis peran, isolasi klien, Segregation of Duties, layar riwayat & jejak audit, dan dashboard antrean.  
* **Review Gate**: Seluruh 8 skenario uji penerimaan lulus sebelum demonstrasi langsung pada Demo Day.

## 

## **8\. Skenario Uji Penerimaan (UAT / Demo Day)**

| No | Skenario | Langkah Uji | Hasil yang Diharapkan |
| :---- | :---- | :---- | :---- |
| 1 | Alur normal | Unggah PDF → AI ekstrak → lolos validasi → reviewer menyetujui. | Voucher PDF resmi terunduh; status SENT\_TO\_CLIENT. |
| 2 | Multi-line item | Unggah invoice dengan ≥ 3 jenis barang. | Seluruh baris terbaca akurat dan total dihitung benar. |
| 3 | Missing evidence | Unggah invoice tanpa nomor rekening. | Ditandai MISSING\_EVIDENCE; status EXCEPTION. |
| 4 | Deteksi duplikasi | Unggah invoice dengan nomor & vendor yang sama dengan dokumen sebelumnya. | Ditandai POSSIBLE\_DUPLICATE. |
| 5 | Segregation of Duties | User A mengunggah, lalu User A mencoba menyetujui. | Sistem menolak persetujuan dan otomatis mengalihkan dokumen ke reviewer lain. |
| 6 | Keamanan multi-klien | User Klien A mencoba membuka dokumen Klien B. | Akses ditolak sepenuhnya. |
| 7 | Penelusuran audit | Reviewer mengubah nominal pada layar review. | Sistem mencatat nilai awal, nilai baru, nama reviewer dan waktu. |
| 8 | Perbaikan setelah EXCEPTION | PIC Klien melengkapi nomor rekening pada dokumen MISSING\_EVIDENCE. | Dokumen kembali ke tahap ekstraksi dengan Request ID yang sama, diverifikasi ulang, lalu berstatus READY\_FOR\_REVIEW. |

## 

## **9\. Glosarium Status & Kode Kendala**

| Istilah | Definisi |
| :---- | :---- |
| **QUEUED** | Dokumen telah diunggah, memiliki Request ID dan menunggu diproses. |
| **PROCESSING** | Mesin AI sedang membaca invoice dan mengisi draf voucher. |
| **READY\_FOR\_REVIEW** | Dokumen lolos seluruh verifikasi sistem dan siap ditinjau Finance Reviewer. |
| **EXCEPTION** | Sistem menemukan kendala (dengan kode dan alasan) atau reviewer mengembalikan dokumen; PIC Klien perlu memperbaikinya sebelum dokumen diproses ulang. |
| **AMIGA\_REVIEWED** | Hasil ekstraksi telah diverifikasi dan disetujui peninjau independen. |
| **SENT\_TO\_CLIENT** | Voucher PDF resmi telah diunduh oleh PIC Klien. |
| **MISSING\_EVIDENCE** | Kode kendala: informasi atau dokumen pendukung wajib tidak ditemukan (misalnya nomor rekening). |
| **POSSIBLE\_DUPLICATE** | Kode kendala: terdapat invoice lain dengan nomor dan vendor yang sama. |
| **CALCULATION\_DISCREPANCY** | Kode kendala: selisih antara penjumlahan subtotal line items dan total invoice; status menjadi EXCEPTION. |
| **Request ID** | Nomor unik yang diterbitkan sistem untuk setiap permintaan pemrosesan invoice. |
| **Segregation of Duties (SoD)** | Pemisahan tugas agar pengunggah dokumen tidak dapat meninjau atau menyetujui dokumen yang sama. |

