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
- Artifact: `diaglob-mobile-v0.1.1-standalone`
- APK: `diaglob-mobile-v0.1.1-standalone.apk`
- Retención: 14 días

El APK se compila en modo release con el bundle JavaScript embebido, por lo que funciona sin Metro ni computador. La firma sigue siendo de pruebas internas; no es todavía el build destinado a Google Play.
