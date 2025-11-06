# Authentication API

**Base path:** `/api/auth/`

## Core Auth

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| POST | `/register/` | Register a new user and trigger email verification. | JSON: `username`, `email`, `password`, `password_confirm`, optional `first_name`, `last_name`. | `201 Created` with `message`, `email`, and `email_sent` flag. Validation errors returned with `errors` map. |
| POST | `/login/` | Email/password login. Handles 2FA hand-off. | JSON: `email`, `password`. | If user has 2FA, returns `200 OK` with `requires_2fa`, `user_id`, `code_already_sent`. Otherwise returns tokens (`refresh`, `access`) and serialized `user`. Errors: `401` invalid creds, `403` email not verified. |
| POST | `/login/verify-2fa/` | Complete login after receiving 2FA code. | JSON: `user_id`, `code`. | `200 OK` with `user`, `refresh`, `access`, `message`. |
| POST | `/token/refresh/` | Obtain a new access token. | JSON: `refresh`. | `200 OK` with new `access` token. |

## Email Verification & Rate Limits

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| POST | `/verify-email/` | Verify email via token sent during registration. | JSON: `token`. | `200 OK` with `message` on success; `400` with `error` on invalid token. |
| POST | `/resend-verification/` | Send another verification email. | JSON: `email`. | `200 OK` with `message`; `429` when rate limited. |
| POST | `/check-rate-limit/` | Check whether email actions are rate limited. | JSON: `email`, optional `request_type` (`email_verification`, `login`, etc.). | `200 OK` with `can_send` and `time_remaining` seconds. |

## Two-Factor Authentication

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| POST | `/2fa/toggle/` | Initiate enabling or disabling 2FA. | JSON: `enable` (bool). Auth required. | `200 OK` with `requires_verification` and email message. Sends code to email. |
| POST | `/2fa/verify/` | Confirm a 2FA action (enable, disable, set password). | JSON: `code`, `purpose` (`enable_2fa`, `disable_2fa`, `set_password`). | `200 OK` with status message and `two_factor_enabled` flag (when toggling). |
| GET | `/2fa/status/` | Fetch current 2FA status. | Auth header. | `200 OK` with `two_factor_enabled`, `email`. |
| POST | `/resend-2fa-code/` | Resend a 2FA code for a pending purpose. | JSON: `user_id`, optional `purpose` (defaults to `login`). | `200 OK` with confirmation message; `429` on rate limit. |

## Password Management

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| POST | `/password/request/` | OAuth users request to set a password (sends 2FA code). | Auth header. Body is empty. | `200 OK` with `requires_verification` flag. |
| POST | `/password/set/` | Set a password for OAuth-only accounts after 2FA. | Auth header. JSON: `code`, `password`, `password_confirm`. | `200 OK` with confirmation and `is_oauth_only_user: false`. |
| POST | `/password/reset/request/` | Begin password reset (all accounts). | JSON: `email`. | `200 OK` cautionary message and `user_id` when applicable. Triggers email. |
| POST | `/password/reset/` | Complete password reset with code. | JSON: `user_id`, `code`, `password`, `confirm_password`. | `200 OK` with confirmation. |

## Profile & Language

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| GET | `/profile/` | Retrieve authenticated user profile. | Auth header. | `200 OK` with `UserSerializer` payload. |
| PATCH | `/profile/` | Update profile fields (partial updates only). | Auth header. JSON payload matching `UserSerializer`; nested `profile` object for profile fields. Some fields restricted to verified sellers. | `200 OK` with updated profile. `403` when non-sellers update restricted fields. |
| POST | `/change-language/` | Update preferred language. | Auth header. JSON: `language` (one of `CustomUser.LANGUAGE_CHOICES`). | `200 OK` with `old_language`, `new_language`, and `user` summary. |
| POST | `/profile/picture/upload/` | Upload profile picture to S3. | Auth header. Multipart with file under `profile_picture` or `image`. Requires `settings.USE_S3`. Max 10 MB. | `200 OK` with stored `profile_picture_url`, temp URL, metadata. |
| DELETE | `/profile/picture/delete/` | Remove current profile picture. | Auth header. | `200 OK` with success message. |
| GET | `/users/{id}/` | Public profile lookup. | Path: integer user ID. Auth optional. | `200 OK` with public profile summary. `404` if user missing. |

## Google OAuth

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| POST | `/google/login/` | Login or auto-register using Google profile data. | JSON per `GoogleAuthSerializer`: `email`, `sub`, optional `given_name`, `family_name`, `picture`, `email_verified`. | `200 OK` with `success`, `tokens`, `user`, `is_new_user`. |
| POST | `/google/register/` | Explicit Google registration (mirrors login). | Same as above. | `200 OK` with tokens and `is_new_user`. |
| POST | `/google-oauth/` | Legacy Google endpoint; auto-creates account as needed. | JSON with at least `email`, optional profile fields. | `200 OK` with `user`, `access`, `refresh`, `is_new_user`. |

## Seller Workflow

All routes below require authentication. Admin-only routes additionally require `user.role == "admin"` or `is_superuser`.

| Method | Path | Description | Request | Success Response |
| --- | --- | --- | --- | --- |
| POST | `/seller/apply/` | Submit seller application. User must have 2FA enabled and not already be a seller/applicant. | Multipart form fields: `businessName`, `sellerType`, `motivation`, optional `portfolio`, `socialMedia`, and zero or more `workshopPhotos`. | `201 Created` with `success`, `message`, `application_id`. |
| GET | `/seller/application/status/` | Check current application status. | Auth header. | `200 OK` with `SellerApplicationSerializer` data or `has_application: false`. |
| GET | `/seller/application/` | Retrieve full application details. | Auth header. | `200 OK` with `SellerApplicationSerializer`. `404` if none submitted. |
| GET | `/user/role/` | Inspect current role flags. | Auth header. | `200 OK` with `id`, `email`, `role`, plus `is_seller`, `is_admin`, `can_sell_products`. |
| GET | `/admin/seller/applications/` | List all seller applications (admin). Supports `status` query filter. | Admin auth. | `200 OK` array of applications ordered by submission date. |
| PATCH | `/admin/seller/applications/{id}/` | Update status/notes on an application. | Admin auth. JSON (`status`, optional `admin_notes`, `rejection_reason`). | `200 OK` with updated application. |
| POST | `/admin/seller/approve/{application_id}/` | Approve the specified application. | Admin auth. Optional JSON body ignored. | `200 OK` with success message. |
| POST | `/admin/seller/reject/{application_id}/` | Reject the specified application. | Admin auth. JSON optional `reason`. | `200 OK` with success message. |
