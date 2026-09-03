# Panduan Pembuatan User Read-Only MikroTik RouterOS

Untuk menjaga keamanan maksimal, buat grup dan user khusus untuk bot dengan hak akses **Read-Only**.

---

## 1. Buat User Group Khusus (`ai-readonly-group`)

Jalankan perintah berikut di Terminal MikroTik (Winbox / SSH):

```routeros
/user group
add name=ai-readonly-group policy=read,api,rest-api,test,!local,!telnet,!ssh,!ftp,!reboot,!write,!policy,!winbox,!password,!web,!sniff,!sensitive,!romon
```

> [!NOTE]
> Policy yang diizinkan hanya:
> - `read` (membaca konfigurasi)
> - `api` & `rest-api` (akses REST endpoint)
> - `test` (ping dan diagnostik)
> 
> Policy `write`, `reboot`, `password`, `sensitive` **dilarang**.

---

## 2. Buat User Baru

```routeros
/user
add name=ai-readonly group=ai-readonly-group password="GantiDenganPasswordKuat" comment="WhatsApp AI Bot Read-Only User"
```

---

## 3. Batasi Akses IP (Opsional namun Sangat Disarankan)

Jika server WhatsApp Assistant memiliki IP statis (misal `192.168.88.50`), batasi login hanya dari IP tersebut:

```routeros
/user
set [find name=ai-readonly] allowed-address=192.168.88.50/32
```

---

## 4. Pastikan Service `www` atau `www-ssl` Aktif

RouterOS v7 menggunakan service `www` (port 80) atau `www-ssl` (port 443) untuk REST API:

```routeros
/ip service
set www disabled=no port=80
```

Atau jika menggunakan HTTPS:

```routeros
/ip service
set www-ssl disabled=no port=443
```
