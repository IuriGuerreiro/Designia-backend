# 🛡️ CSP, CORS & Security Policies Guide

**THE ULTIMATE GUIDE TO FIX "REFUSED TO CONNECT" ERRORS AND STRIPE/EXTERNAL SERVICE INTEGRATION**

---

## 🚨 **COMMON ERRORS THIS FIXES:**

- ❌ `Refused to connect to 'https://js.stripe.com/v3'`
- ❌ `Content Security Policy directive violation`
- ❌ `Cross-Origin Request Blocked`
- ❌ Stripe/PayPal/Google APIs not loading
- ❌ External scripts/fonts/images blocked
- ❌ Embedded iframes not working

---

## 📍 **FOR DJANGO/PYTHON PROJECTS**

### **File: `settings.py`**
```python
# CORS Settings
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",  # Vite
    "http://127.0.0.1:5173",
    "https://yourdomain.com",
]

CORS_ALLOW_CREDENTIALS = True

# CSP Settings (using django-csp package)
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = (
    "'self'",
    "'unsafe-inline'",
    "'unsafe-eval'",
    "https://js.stripe.com",
    "https://accounts.google.com",
    "https://apis.google.com",
    "https://www.paypal.com",
)
CSP_CONNECT_SRC = (
    "'self'",
    "https://api.stripe.com",
    "https://accounts.google.com",
    "https://www.paypal.com",
)
CSP_FRAME_SRC = (
    "'self'",
    "https://js.stripe.com",
    "https://hooks.stripe.com",
    "https://accounts.google.com",
    "https://www.paypal.com",
)
CSP_STYLE_SRC = (
    "'self'",
    "'unsafe-inline'",
    "https://fonts.googleapis.com",
)
CSP_FONT_SRC = (
    "'self'",
    "https://fonts.gstatic.com",
)
CSP_IMG_SRC = (
    "'self'",
    "data:",
    "https:",
)

# Security Headers Middleware
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"
SECURE_CROSS_ORIGIN_EMBEDDER_POLICY = None  # Don't use 'require-corp'
```

### **Install Required Package:**
```bash
pip install django-cors-headers django-csp
```

### **Add to MIDDLEWARE in settings.py:**
```python
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'csp.middleware.CSPMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # ... other middleware
]
```

---

## 📍 **FOR EXPRESS.JS/NODE.JS PROJECTS**

### **File: `server.js` or `app.js`**
```javascript
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');

const app = express();

// CORS Configuration
app.use(cors({
  origin: [
    'http://localhost:3000',
    'http://localhost:5173',
    'https://yourdomain.com'
  ],
  credentials: true
}));

// Security Headers with CSP
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: [
        "'self'",
        "'unsafe-inline'",
        "'unsafe-eval'",
        "https://js.stripe.com",
        "https://accounts.google.com",
        "https://www.paypal.com"
      ],
      connectSrc: [
        "'self'",
        "https://api.stripe.com",
        "https://accounts.google.com",
        "https://www.paypal.com"
      ],
      frameSrc: [
        "'self'",
        "https://js.stripe.com",
        "https://hooks.stripe.com",
        "https://accounts.google.com",
        "https://www.paypal.com"
      ],
      styleSrc: [
        "'self'",
        "'unsafe-inline'",
        "https://fonts.googleapis.com"
      ],
      fontSrc: [
        "'self'",
        "https://fonts.gstatic.com"
      ],
      imgSrc: [
        "'self'",
        "data:",
        "https:"
      ]
    }
  },
  crossOriginOpenerPolicy: { policy: "same-origin-allow-popups" },
  crossOriginEmbedderPolicy: false, // Don't enable this
}));
```

---

## 🔧 **COMMON CSP DIRECTIVES EXPLAINED**

| Directive | Purpose | Common Values |
|-----------|---------|---------------|
| `default-src` | Default policy for all resource types | `'self'` |
| `script-src` | JavaScript sources | `'self'`, `'unsafe-inline'`, `https://js.stripe.com` |
| `connect-src` | AJAX, WebSocket, EventSource | `'self'`, `https://api.stripe.com` |
| `frame-src` | `<iframe>` sources | `'self'`, `https://js.stripe.com` |
| `style-src` | CSS sources | `'self'`, `'unsafe-inline'`, `https://fonts.googleapis.com` |
| `font-src` | Font sources | `'self'`, `https://fonts.gstatic.com` |
| `img-src` | Image sources | `'self'`, `data:`, `https:` |
| `object-src` | `<object>`, `<embed>`, `<applet>` | `'none'` (usually blocked) |

---

## ⚡ **QUICK FIX TEMPLATES**

### **For Stripe Integration:**
```
script-src: https://js.stripe.com
connect-src: https://api.stripe.com
frame-src: https://js.stripe.com https://hooks.stripe.com
```

### **For Google OAuth/APIs:**
```
script-src: https://accounts.google.com https://apis.google.com
connect-src: https://accounts.google.com
frame-src: https://accounts.google.com
```

### **For PayPal:**
```
script-src: https://www.paypal.com https://www.paypalobjects.com
connect-src: https://www.paypal.com
frame-src: https://www.paypal.com
```

### **For Font/Style Libraries:**
```
style-src: https://fonts.googleapis.com https://cdn.jsdelivr.net
font-src: https://fonts.gstatic.com https://cdn.jsdelivr.net
```

---

## 🚨 **CRITICAL WARNINGS**

### **❌ DON'T DO THIS:**
```python
# This BREAKS external services like Stripe
SECURE_CROSS_ORIGIN_EMBEDDER_POLICY = "require-corp"
SECURE_CROSS_ORIGIN_EMBEDDER_POLICY = "credentialless"

# This is TOO RESTRICTIVE
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'",)  # No external scripts allowed
```

### **✅ DO THIS:**
```python
# This ALLOWS external services
SECURE_CROSS_ORIGIN_EMBEDDER_POLICY = None

# This is PERMISSIVE for external services
CSP_SCRIPT_SRC = ("'self'", "https://js.stripe.com", "https://accounts.google.com")
```

---

## 🚀 **PRODUCTION DEPLOYMENT**

### **Environment Variables:**
```bash
# Development (permissive)
CSP_SCRIPT_SRC="'self' 'unsafe-inline' 'unsafe-eval' https:"

# Production (restrictive)
CSP_SCRIPT_SRC="'self' https://js.stripe.com https://accounts.google.com"
```

### **Nginx Configuration:**
```nginx
location / {
    add_header Cross-Origin-Opener-Policy "same-origin-allow-popups" always;
    add_header Cross-Origin-Embedder-Policy "unsafe-none" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://js.stripe.com; connect-src 'self' https://api.stripe.com;" always;
}
```

### **Apache Configuration:**
```apache
<LocationMatch ".*">
    Header always set Cross-Origin-Opener-Policy "same-origin-allow-popups"
    Header always set Cross-Origin-Embedder-Policy "unsafe-none"
    Header always set Content-Security-Policy "default-src 'self'; script-src 'self' https://js.stripe.com; connect-src 'self' https://api.stripe.com;"
</LocationMatch>
```

---

## 🎯 **FINAL REMINDER**

**THE #1 CAUSE OF "REFUSED TO CONNECT" ERRORS:**

1. **`Cross-Origin-Embedder-Policy: credentialless`** ← Change to `unsafe-none`
2. **Missing external domains in CSP** ← Add `https://js.stripe.com` etc.
3. **Too restrictive CSP** ← Allow `'unsafe-inline'` for development

**ALWAYS RESTART YOUR DEV SERVER AFTER CHANGING THESE FILES!**

---

*Save this guide - it will save your ass when external services break! 🛡️*