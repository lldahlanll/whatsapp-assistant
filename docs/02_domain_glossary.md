# DOC-002 · Domain Glossary (Ubiquitous Language)

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Domain Architect  

---

## Aturan Penggunaan Glossary Ini

1. **Semua nama class, method, variable, dan folder HARUS menggunakan term dari dokumen ini.**
2. Jika ada term baru yang ditemukan saat development, tambahkan di sini sebelum coding.
3. Term yang berbeda bahasa (Inggris vs Indonesia) harus diklarifikasi konteksnya.
4. Jika ada ambiguitas, refer ke dokumen ini — bukan ke intuisi masing-masing.

---

## A

### `Agent`
- **Definisi:** Entitas software yang bertindak atas nama manusia untuk mengirim/menerima pesan dan menjalankan logika bisnis.
- **Dalam kode:** `class Agent` — orchestrator utama yang menghubungkan Session dengan FeatureRegistry.
- **Bukan:** Bukan AI Agent secara spesifik; `AIAgent` adalah turunan yang lebih spesifik.

### `Aggregate`
- **Definisi:** Cluster entitas dan value objects yang diperlakukan sebagai satu unit untuk operasi data. Setiap aggregate memiliki satu `Aggregate Root`.
- **Contoh:** `Conversation` adalah aggregate yang berisi koleksi `Message`.

### `Aggregate Root`
- **Definisi:** Entitas utama dalam sebuah aggregate yang menjadi satu-satunya titik masuk dari luar.
- **Contoh:** `WhatsAppSession` adalah aggregate root dari session.

---

## B

### `BotCommand`
- **Definisi:** Value object yang merepresentasikan perintah terstruktur yang diekstrak dari pesan masuk.
- **Properti:** `prefix: str`, `name: str`, `args: list[str]`, `raw: str`
- **Contoh:** Dari pesan `!help menu`, menghasilkan `BotCommand(prefix="!", name="help", args=["menu"])`.

### `Broadcast`
- **Definisi:** Pengiriman pesan ke banyak penerima dalam satu operasi terjadwal.
- **Bukan:** Bukan WhatsApp Broadcast List (fitur native WA). Ini adalah konsep platform kita.

---

## C

### `Client`
- **Definisi:** Instance dari Neonize yang terhubung ke satu nomor WhatsApp. Ini adalah layer paling rendah yang berinteraksi langsung dengan protokol WhatsApp.
- **Dalam kode:** Diakses hanya melalui `INeonizeGateway` interface, tidak pernah langsung.
- **Bukan:** Bukan `User` atau `Contact`. `Client` adalah representasi nomor yang kita kontrol.

### `Command`
- **Definisi (Domain):** Instruksi dari user yang mengharapkan aksi dari bot. Dimulai dengan prefix tertentu (default: `!`).
- **Definisi (CQRS):** Objek yang merepresentasikan intent untuk mengubah state.
- **Context:** Ketika disebut tanpa konteks, selalu merujuk ke definisi Domain.

### `CommandHandler`
- **Definisi:** Callable yang bertanggung jawab menangani satu atau lebih `BotCommand` spesifik.
- **Interface:** `async def handle(ctx: CommandContext) -> None`

### `CommandRouter`
- **Definisi:** Application service yang menerima `IncomingMessage`, memeriksa apakah ia adalah command, dan mendelegasikan ke `CommandHandler` yang tepat.

### `Contact`
- **Definisi:** Entity yang merepresentasikan pengguna WhatsApp lain yang berinteraksi dengan bot kita.
- **Properti:** `jid: JID`, `name: str | None`, `phone: str`, `is_group: bool`
- **Bukan:** Bukan `User` internal sistem kita.

### `Conversation`
- **Definisi:** Aggregate yang merepresentasikan thread percakapan antara Contact dan platform kita, termasuk histori pesan.
- **Aggregate Root:** `Conversation`

---

## D

### `DomainEvent`
- **Definisi:** Fakta yang telah terjadi dalam domain, dideskripsikan dalam past tense.
- **Contoh:** `MessageReceived`, `SessionConnected`, `CommandExecuted`
- **Aturan:** Domain events tidak boleh memiliki side effects langsung. Side effects dijalankan oleh event handlers.

---

## E

### `EventBus`
- **Definisi:** Mekanisme pub/sub internal untuk mempropagasikan domain events ke semua subscribers yang relevan.
- **Dalam kode:** `class InMemoryEventBus` implements `IEventBus`

### `EventHandler`
- **Definisi:** Callable async yang berlangganan pada satu jenis `DomainEvent` dan bereaksi terhadapnya.
- **Interface:** `async def handle(event: DomainEvent) -> None`

---

## F

### `Feature`
- **Definisi:** Satu modul fungsional yang dapat ditambahkan atau dihapus dari platform tanpa memengaruhi feature lain.
- **Struktur:** Setiap feature berada dalam folder `src/features/<feature_name>/`
- **Contoh:** `session`, `messaging`, `commands`, `ai_integration`, `scheduler`

### `FeatureRegistry`
- **Definisi:** Registry yang mengelola semua feature yang aktif dan menghubungkannya ke event bus.

---

## G

### `Gateway`
- **Definisi:** Adapter pattern yang membungkus Neonize (atau library eksternal lainnya) agar dapat digunakan dari dalam application layer melalui interface.
- **Dalam kode:** `class NeonizeGateway` implements `IMessagingGateway`

---

## H

### `Handler`
- **Definisi (umum):** Callable yang memproses satu jenis input (event, command, atau message).
- **Lihat juga:** `CommandHandler`, `EventHandler`, `MessageHandler`

---

## I

### `IncomingMessage`
- **Definisi:** Value object yang merepresentasikan pesan yang diterima dari WhatsApp, sudah dinormalisasi dari format Neonize ke format domain kita.
- **Properti:** `id: MessageID`, `from_jid: JID`, `body: str | None`, `media: MediaContent | None`, `timestamp: datetime`, `is_group: bool`, `reply_to: MessageID | None`

### `Infrastructure`
- **Definisi:** Layer terluar dalam Clean Architecture yang berisi implementasi konkret dari interfaces yang didefinisikan di domain/application layer.
- **Contoh:** `NeonizeGateway`, `SQLAlchemyMessageRepository`, `ARQTaskQueue`

---

## J

### `JID`
- **Definisi:** *Jabber ID* — identifier unik untuk entitas di jaringan WhatsApp.
- **Format:** `<nomor_telepon>@s.whatsapp.net` untuk personal, `<group_id>@g.us` untuk group
- **Dalam kode:** Adalah type alias `type JID = str` atau value object `class JID`

---

## M

### `MediaContent`
- **Definisi:** Value object yang merepresentasikan konten media dalam pesan (gambar, video, dokumen, audio).
- **Properti:** `mime_type: str`, `file_size: int`, `caption: str | None`, `url: str | None`

### `Message`
- **Definisi:** Entity yang merepresentasikan satu pesan dalam sebuah Conversation.
- **Variant:** `TextMessage`, `MediaMessage`, `StickerMessage`, `PollMessage`

### `MessageID`
- **Definisi:** Value object yang merupakan identifier unik untuk setiap pesan.
- **Dalam kode:** `type MessageID = str`

### `MessageStatus`
- **Definisi:** Value object yang merepresentasikan status pengiriman pesan.
- **Values:** `PENDING`, `SENT`, `DELIVERED`, `READ`, `FAILED`

### `Middleware`
- **Definisi:** Komponen yang memproses pesan/request sebelum atau sesudah handler utama. Dapat melakukan logging, rate limiting, auth check, dll.
- **Pattern:** Chain of responsibility.

---

## O

### `OutgoingMessage`
- **Definisi:** Value object yang merepresentasikan pesan yang akan dikirim ke WhatsApp, sebelum diserahkan ke Gateway.
- **Properti:** `to_jid: JID`, `body: str | None`, `media: MediaContent | None`, `reply_to: MessageID | None`

---

## P

### `Platform`
- **Definisi (domain):** Keseluruhan sistem yang kita bangun — bukan hanya bot, tapi ekosistem fitur, konfigurasi, dan integrasi.

### `Plugin`
- **Definisi:** Synonym dari `Feature` untuk konteks yang lebih teknis. Digunakan ketika mengacu pada modul yang bisa di-load secara dinamis.

---

## R

### `Repository`
- **Definisi:** Interface yang mendefinisikan kontrak untuk operasi persistence (simpan, ambil, hapus) pada aggregate tertentu.
- **Aturan:** Interfaces didefinisikan di `domain/repositories/`, implementasi di `infrastructure/database/`.

### `Router`
- **Definisi:** Komponen yang menentukan handler mana yang harus memproses input tertentu berdasarkan aturan yang didefinisikan.

---

## S

### `Session`
- **Definisi:** Entity yang merepresentasikan koneksi aktif antara platform kita dengan satu akun WhatsApp. Berisi state koneksi, credential, dan metadata.
- **Lifecycle:** `INITIALIZING` → `AUTHENTICATING` (QR) → `CONNECTED` → `DISCONNECTED` → `RECONNECTING`

### `SessionStatus`
- **Definisi:** Value object untuk status lifecycle dari `Session`.
- **Values:** `INITIALIZING`, `AWAITING_QR`, `CONNECTED`, `DISCONNECTING`, `DISCONNECTED`, `RECONNECTING`, `FAILED`

---

## U

### `UseCase`
- **Definisi:** Application service yang mengeksekusi satu skenario bisnis spesifik. Mengkoordinasikan domain entities dan repositories.
- **Naming convention:** `<Verb><Noun>UseCase` — contoh: `SendMessageUseCase`, `ParseCommandUseCase`

---

## V

### `ValueObject`
- **Definisi:** Objek yang tidak memiliki identitas (tidak ada ID), bersifat immutable, dan didefinisikan sepenuhnya oleh atributnya.
- **Contoh:** `JID`, `MessageID`, `MessageStatus`, `BotCommand`

---

## W

### `WhatsAppEvent`
- **Definisi:** Event raw yang datang dari Neonize (Go backend). Harus segera di-map ke domain event sebelum diserahkan ke application layer.
- **Contoh Neonize events:** `MessageEv`, `ReceiptEv`, `ConnectedEv`, `DisconnectedEv`, `QREv`

### `Worker`
- **Definisi:** Proses async yang mengkonsumsi task dari queue dan mengeksekusinya. Bertanggung jawab atas heavy processing yang tidak boleh dilakukan di event handler langsung.

---

## Mapping: Neonize Term → Domain Term

| Neonize / WhatsApp Term | Domain Term Kita | Catatan |
|------------------------|------------------|---------|
| `NewAClient` | `NeonizeGateway` | Selalu via interface |
| `MessageEv` | `IncomingMessage` | Setelah mapping |
| `JID` | `JID` | Sama, tapi kita buat type alias sendiri |
| `ReceiptEv` | `MessageStatusUpdated` (DomainEvent) | |
| `ConnectedEv` | `SessionConnected` (DomainEvent) | |
| `DisconnectedEv` | `SessionDisconnected` (DomainEvent) | |
| `QREv` | `QRCodeGenerated` (DomainEvent) | |
| `GroupInfo` | `Group` (Entity) | |

---

## References

- [DOC-001: Product Vision](./01_product_vision.md)
- [DOC-005: Architecture Overview](./05_architecture_overview.md)
- [DOC-008: Domain Model](./07_domain_model.md)
- [DOC-014: Event Catalog](./12_event_catalog.md)
