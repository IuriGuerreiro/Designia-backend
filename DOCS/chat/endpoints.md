# Chat API

**Base path:** `/api/chat/`

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/` | List chats for the authenticated user. | Auth header. Supports pagination defaults. | `200 OK` with array of `ChatSerializer` objects (`id`, `other_user`, `last_message`, `unread_count`, etc.). |
| POST | `/` | Create (or fetch) a chat with another user. | Auth header. JSON: `user_id` (target user). | `201 Created` when new chat, `200 OK` when existing; returns `ChatSerializer` payload. Also triggers websocket notifications. |
| GET | `/{chat_id}/` | Retrieve chat metadata. | Auth header. Path int `chat_id`. | `200 OK` with `ChatSerializer`. `404` if chat not found or user not participant. |
| GET | `/{chat_id}/messages/` | List messages in a chat. | Auth header. Query: `page`, optional `page_size` (max 100). | `200 OK` paginated list ordered newest first (`MessageSerializer`). |
| POST | `/{chat_id}/messages/` | Send a message in the chat. | Auth header. JSON: `message_type` (`text` or `image`), `text_content` (for text), `image_url` (for image). | `201 Created` with `MessageSerializer`. Notifies recipient via websocket. |
| POST | `/{chat_id}/messages/mark-read/` | Mark all messages as read for current user. | Auth header. | `200 OK` with `message` describing count. |
| POST | `/upload-image/` | Upload chat image to S3 and obtain URL. | Auth header. Multipart file field `image` (<=10 MB; jpeg/png/webp). Requires S3 enabled. | `200 OK` with stored `image_url` key, `image_temp_url`, metadata. |
| GET | `/search-users/` | Search for users to start a chat. | Auth header. Query: `q` (required). | `200 OK` with `users` array using `ChatUserSerializer`. |
