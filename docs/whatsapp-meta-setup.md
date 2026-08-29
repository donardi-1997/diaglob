# WhatsApp Cloud API — Meta Developer Setup

Guide paso a paso para conectar DIAGLOB con WhatsApp Cloud API de Meta.

---

## 1. Crear Meta App

1. Ir a [developers.facebook.com](https://developers.facebook.com/)
2. Click **"Crear app"** → selecciona tipo **"Business"**
3. Nombre: `DIAGLOB` (o el que prefieras)
4. Email de contacto: tu email
5. Click **"Crear app"**

## 2. Añadir producto WhatsApp

1. En el dashboard del app, click **"Agregar producto"**
2. Busca **"WhatsApp"** → click **"Configurar"**
3. Selecciona o crea un **WhatsApp Business Account** existente

## 3. Obtener credenciales

### Phone Number ID

1. En **WhatsApp > Configuración > Accounts**
2. Selecciona tu Business Account
3. En **"Phone numbers"** verás el **Phone Number ID** (formato: número largo, ej. `106540352242922`)

### WhatsApp Business Account ID

1. En **WhatsApp > Configuración > Accounts**
2. El ID del Business Account aparece en la URL o en la configuración
3. Formato: número largo (ej. `102290129340398`)

### Access Token

**Token temporal (para pruebas):**
1. En **WhatsApp > Getting Started > API Setup**
2. Click **"Generate temporary token"**
3. Copia el token (expira en ~24 horas)
4. **Nunca lo guardes en código fuente ni en el frontend**

**Token permanente (producción):**
1. En **WhatsApp > Getting Started > API Setup**
2. Selecciona **"System User"** o crea uno
3. Asigna permisos: `whatsapp_business_messaging`, `whatsapp_business_management`
4. Genera token del System User
5. **Este token no expira pero puede ser revocado**

### App Secret

1. En **Settings > Basic**
2. Click **"Show"** junto a **App Secret**
3. Copia el valor
4. **Este valor NUNCA va en el frontend. Solo en la variable de entorno del backend.**

## 4. Variables de entorno del backend

Agregar al `.env` del backend:

```bash
# App Secret de Meta (solo backend)
WHATSAPP_APP_SECRET=a1b2c3d4e5f6...

# Clave de cifrado para tokens de WhatsApp
WHATSAPP_TOKEN_ENCRYPTION_KEY=<fernet_key>

# Versión de Graph API (opcional, default v21.0)
WHATSAPP_GRAPH_API_VERSION=v21.0
```

Generar Fernet key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 5. Configurar Webhook en Meta

### URL del webhook

```
https://api.diaglob.tech/api/webhooks/whatsapp
```

### Verify Token

El verify token se genera automáticamente por DIAGLOB al conectar cada Store.
Se encuentra en **Integraciones > WhatsApp > Verify Token** después de conectar.

### Pasos en Meta

1. En **WhatsApp > Configuration > Webhooks**
2. Click **"Callback URL"** → pega la URL del webhook
3. Pega el **Verify Token** de DIAGLOB
4. Click **"Verify and save"**
5. Suscribirse al campo:
   - **`messages`** — recibe mensajes entrantes y estados de mensajes salientes (sent/delivered/read/failed)

## 6. Diferencia entre token temporal y permanente

| Característica | Token temporal | Token permanente |
|---|---|---|
| Duración | ~24 horas | No expira |
| Uso | Pruebas y desarrollo | Producción |
| Generado por | Botón en dashboard | System User |
| Riesgo | Se vence frecuentemente | Requiere rotación manual si se compromete |

**Recomendación:**
- Usa token temporal para probar la conexión inicial
- Para producción, genera un token de System User con permisos `whatsapp_business_messaging` y `whatsapp_business_management`

## 7. Campos de webhook a suscribir

En Meta Developers > WhatsApp > Configuration > Webhooks:

| Campo | Evento | Qué recibe |
|---|---|---|
| `messages` | `messages` | Mensajes entrantes del usuario (texto, imagen, etc.) |
| `messages` | `statuses` | Estados de mensajes salientes (sent, delivered, read, failed) |

## 8. Verificar la conexión

1. En DIAGLOB, ve a **Tiendas > [Tu tienda] > Integraciones > WhatsApp**
2. Ingresa Phone Number ID, Business Account ID y Access Token
3. Click **"Conectar"**
4. Copia el Verify Token mostrado
5. En Meta, configura el webhook con ese token
6. Envía un mensaje de WhatsApp a tu número de Business
7. El mensaje debe aparecer en **DIAGLOB > Inbox**

## 9. Seguridad

- **App Secret** → solo en backend (`WHATSAPP_APP_SECRET`), nunca en frontend
- **Access Token** → cifrado con Fernet en la base de datos, nunca visible después de guardar
- **Verify Token** → único por conexión, visible solo al owner en el panel de integraciones
- **Webhook** → validado con HMAC-SHA256 usando App Secret
- **Nunca** loguear tokens, passwords, ni payloads completos con PII

## 10. Troubleshooting

| Problema | Solución |
|---|---|
| Webhook no verifica | Verificar que el verify_token coincida exactamente |
| Mensajes no llegan | Verificar suscripción al campo `messages` en Meta |
| Error 401 en webhook | App Secret no configurado o incorrecto en `WHATSAPP_APP_SECRET` |
| Error 403 en envío | Token expirado o sin permisos `whatsapp_business_messaging` |
| "Phone number already in use" | Este número ya está conectado a otra tienda en DIAGLOB |
