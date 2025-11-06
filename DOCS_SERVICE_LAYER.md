Service Layer Overview

Goals
- Increase developer velocity by moving business logic out of views and serializers.
- Make logic easier to test and reuse across endpoints.
- Reduce accidental logging of sensitive data by centralizing key flows.

What’s Included
- Shared utilities: `utils/service_base.py` with `ServiceResult`, `service_ok`, and `service_err`.
- App packages:
  - authentication/services (Google OAuth service)
  - marketplace/services (product helpers)
  - payment_system/services (Stripe event utilities)
  - chat/services, activity/services (ready for use)

How to Migrate Incrementally
1) Identify a complex method in a view/serializer.
2) Move business logic into `app/services/<topic>.py` as a function or small class.
3) Keep views/serializers focused on I/O and permissions; call the service.
4) Prefer returning `ServiceResult` for expected failures.

Example (Authentication)
- `authentication/google_auth.py` now delegates to `authentication/services/google_oauth.py`.

Example (Marketplace)
- `marketplace/services/product.py` provides `create_product(user, validated_data)`
  and `attach_uploaded_images(...)`. Migrate uploads in small steps as needed.

Example (Payments)
- `payment_system/services/stripe_events.py` offers a safe event summary and
  a single `handle_event(event)` dispatcher. Call this from webhooks as logic
  is moved over.

Testing
- Write tests against service functions instead of views when possible. This
  reduces setup and speeds iteration.
