# Stripe Webhooks Guide with Ngrok

This guide explains how to set up and test Stripe webhooks for the Designia backend using Ngrok.

## 1. Install Ngrok

First, you need to install Ngrok on your system. Follow the official instructions for your operating system: [https://ngrok.com/download](https://ngrok.com/download)

After installing, you may need to authenticate your Ngrok agent. Follow the instructions on the Ngrok dashboard.

## 2. Start your local server

Ensure your Designia-backend Django development server is running:

```bash
python manage.py runserver
```

By default, it will be running on `http://127.0.0.1:8000`.

## 3. Expose your local server with Ngrok

Open a new terminal window and run the following command to create a public tunnel to your local server on port 8000:

```bash
ngrok http 8000
```

Ngrok will display a public URL (e.g., `https://<random-string>.ngrok.io`) that forwards to your local server. Keep this terminal window open.

## 4. Configure Stripe Webhook Endpoint

1.  Go to your Stripe Dashboard.
2.  Navigate to **Developers > Webhooks**.
3.  Click **"Add an endpoint"**.
4.  For the **"Endpoint URL"**, use the public URL from Ngrok, followed by the webhook path for the Designia backend:
    `https://<random-string>.ngrok.io/api/v1/payments/webhooks/`
5.  Select the events you want to listen to (e.g., `payment_intent.succeeded`).
6.  Click **"Add endpoint"**.

## 5. Set up Webhook Signing Secret

After creating the endpoint, Stripe will reveal a **signing secret** (e.g., `whsec_...`).

You need to add this to your `.env` file in the `Designia-backend` directory:

```
STRIPE_WEBHOOK_SECRET=whsec_...
```

Restart your Django server after updating the `.env` file to ensure it loads the new secret.

## 6. Testing the Webhook

You can trigger test events from the Stripe Dashboard.

1.  Go to the webhook endpoint you just created in the Stripe Dashboard.
2.  Click the **"Send test webhook"** button.
3.  Select an event (all the ones on the endpoints) and send it.

You should see the request being received in the Ngrok terminal window and your Django server console should show the request being processed.

By following these steps, you can effectively develop and test Stripe webhooks for the Designia backend using Ngrok.