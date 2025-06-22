# DropOff-Zone-Violation-Detection

Sistem deteksi pelanggaran kendaraan yang berhenti terlalu lama di area drop-off berbasis Raspberry Pi. Proyek ini dirancang untuk membantu pengelola area dalam memantau durasi parkir kendaraan, memberikan peringatan suara secara otomatis melalui speaker, dan mengurangi kemacetan akibat pelanggaran zona drop-off.


## Anggota Kelompok 5

| Nama                     | NIM         |
|--------------------------|-------------|
| Restu Ramadhan Jamaluddin | 426 22 009  |
| Atika Amelia. B           | 426 22 024  |
| Muh. Syawal               | 426 22 025  |
| Nailah Tsabitah. M        | 426 23 026  |
| Sahra Zulqaidah           | 426 23 027  |


## 🔍 Deskripsi Proyek

Sistem ini memanfaatkan kamera yang terhubung ke Raspberry Pi untuk mendeteksi keberadaan kendaraan di zona drop-off. Jika kendaraan berada di area tersebut melebihi batas waktu yang ditentukan, sistem akan memberikan peringatan suara melalui speaker dan mengirimkan notifikasi lanjutan apabila peringatan tidak diindahkan.

### Fitur Utama:

- 🚘 Deteksi kendaraan secara real-time menggunakan kamera.
- ⏱️ Timer untuk mengukur durasi kendaraan berada di zona drop-off.
- 🔊 Peringatan suara otomatis melalui speaker.
- ⚠️ Notifikasi tambahan via telegram kepada satpam untuk tindak lanjut apabila peringatan suara tidak diindahkan.

## Teknologi yang Digunakan

- Raspberry Pi 4
- Python + OpenCV
- YOLO (You Only Look Once) untuk deteksi kendaraan
- Speaker untuk output peringatan suara
- Timer pelanggaran
- Flask Web Server + Telegram API untuk notifikasi lanjutan


