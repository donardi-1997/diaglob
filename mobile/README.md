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
