# Diaglob Mobile

Aplicación operativa de Diaglob para Android e iOS.

## Stack

- Expo SDK 57
- React Native 0.86
- Expo Router
- Expo SecureStore
- Backend existente de Diaglob

## Ejecutar

Requiere Node.js 22.13 o superior.

```bash
cd mobile
cp .env.example .env
npm install
npx expo start
```

La configuración por defecto apunta a `https://api.diaglob.tech`.

## V0

- Inicio operativo
- Pedidos
- Clientes
- Copiloto IA
- Cambio de tienda
- Inicio/cierre de sesión

Los tokens Cognito se almacenan en SecureStore, no en almacenamiento plano.


## APK interno para Android

Cada cambio en `mobile/**` que llega a `main` genera un APK de prueba mediante GitHub Actions:

- Workflow: `Build Diaglob Mobile APK`
- Artifact: `diaglob-mobile-v0.1-internal`
- APK: `diaglob-mobile-v0.1-internal.apk`
- Retención: 14 días

Este APK usa firma de debug y está pensado únicamente para pruebas internas. No es el build destinado a Google Play.
