# Diaglob — Design System

**Versión:** 1.0 (octubre de 2026)  
**Producto:** plataforma de ecommerce y dropshipping para emprendedores de LATAM.  
**Objetivo:** que cualquier comerciante entienda qué puede hacer Diaglob, visualice su negocio y automatice tareas sin interpretar lenguaje de desarrolladores.

## Dirección visual

El sistema toma **patrones**, no piezas copiadas, de tres referencias:

- **Notion:** claridad editorial, superficies cálidas, navegación acogedora, lenguaje simple.
- **Stripe:** KPI legibles, números destacados, feedback operativo, controles previsibles.
- **Intercom:** conversaciones centradas en la tarea, ayudas en contexto y estados comprensibles.
- **Linear / n8n:** densidad controlada y señales de ejecución para el editor de flujos.

Referencias de exploración: https://styles.refero.design/

La identidad de Diaglob conserva el **violeta**. No adoptar verdes o amarillos como nuevos colores principales: son colores funcionales de éxito y aviso.

## Tokens de la interfaz

Los tokens viven en `frontend/src/design-system.css` y sobreescriben de manera conservadora los existentes. Los componentes deben reutilizar los tokens actuales `--bg`, `--panel`, `--border`, `--text`, `--text-secondary`, `--accent` y `--dg-shell-*`.

| Rol | Claro | Uso |
| --- | --- | --- |
| Fondo | `#f8f8f6` | Área principal |
| Tarjetas | `#ffffff` | Paneles y overlays |
| Texto principal | `#212231` | Titulares y datos |
| Texto secundario | `#5d6271` | Descripciones |
| Borde | `#e7e7e9` | Contornos sin ruido |
| Primario | `#6553eb` | CTA, foco, enlaces activos |
| Primario suave | `#edeafe` | Estado seleccionado |
| Éxito | verde | Indicador de operación exitosa, no mero adorno |
| Advertencia | ámbar | Riesgos que necesitan atención |

**Radio:** 10px controles, 14px compactos, 20px tarjetas y 26px superficies destacadas.  
**Espaciado:** escala base 4/8/12/16/24/32/48px.  
**Sombra:** `--ds-shadow-card`, no relieves intensos en todas las cajas.  
**Tipo:** pila Inter / system-ui preexistente; títulos con tracking ligeramente negativo; no introducir tipografías externas por estética.

## Comportamiento

- **Tema:** claro predeterminado únicamente para sesiones sin preferencia guardada. Una elección previa clara u oscura se respeta; el atributo `data-theme` se establece antes del primer render.
- **Navegación:** mantener los grupos, permisos, selector de tienda, búsqueda, menú móvil y colapso lateral existentes.
- **Dashboard:** KPI con valor grande, etiqueta y contexto; distinguir categorías con color secundario accesible, sin depender solo del color.
- **Landing:** titular comercial, CTA inequívoco, demostración visual de producto y tarjetas simples. Evitar acrónimos técnicos en la comunicación orientada al comprador.
- **Automatizaciones:** preservar arrastrar y soltar, nodos, enlaces y debugger. Los bordes, superficies y puntos de la cuadrícula son decorativos.
- **Copiloto:** no alterar streaming, contexto, aprobaciones, controles de panel ni lógica de acciones.
- **Integraciones:** distinguir conexión real, error y pendiente; no confundir estilo visual con estado operativo.

## Accesibilidad y responsive

- Controles importantes deben admitir teclado y foco visible de 3px.
- Objetivo mínimo de 44px para acciones móviles primarias.
- No transmitir estados únicamente con color; conservar iconos y texto.
- Mantener diseño útil desde 320px hasta escritorio ancho.
- Respetar `prefers-reduced-motion`; animaciones decorativas no son esenciales.
- Mantener contenido y navegación disponibles tanto en tema claro como oscuro.
- Evitar gráficos o métricas simuladas fuera de los ejemplos declaradamente ilustrativos.

## Coherencia con las páginas públicas

La landing activa se renderiza desde `PublicLandingPage.tsx` y sus clases empiezan por `marketing-*`. Los estilos `landing-*` pertenecen a una capa anterior y no deben considerarse suficientes para validar cambios en la página pública.

La configuración visual compartida afecta `/` y `/ecommerce`. En landing, login, documentos legales y política de reembolsos, **el tema claro debe ser el predeterminado cuando no existe preferencia almacenada**; el tema oscuro sigue disponible.

Las pruebas de diseño deben comprobar tanto la presencia de los selectores **reales** como la preferencia coherente de cada ruta pública.

## Aplicación en el repositorio

- `frontend/src/design-system.css`: nueva capa de diseño con selectores acotados.
- `frontend/src/App.tsx`: importación de la capa y tema inicial claro.
- `frontend/src/main.tsx`: tema resuelto antes de montar React.
- Componentes ya existentes: **AppShellV2**, **DashboardPage**, **PublicLandingPage**, **IntegrationsHubPage**, **FlowBuilder** y **AgentChatPage**.

No hay cambios en servicios, contratos API ni modelo de datos.

## Checklist de aceptación (QA)

1. `npm run build`, `npm run lint` y `npm run test` dentro de `frontend/`.
2. Landing `/`: hero, menú móvil, idioma, CTA, sección de planes.
3. Dashboard `/app/dashboard`: KPIs, estados vacíos, carga y enlaces operativos.
4. Automatizaciones: crear, arrastrar, conectar, guardar y ejecutar un flujo; comprobar el canvas al redimensionar.
5. Copiloto: abrir/cerrar, arrastrar y redimensionar, navegación contextual, streaming y aprobación de acciones.
6. Integraciones: tarjetas conectadas y desconectadas, selección de tienda, estados de error.
7. Vista 320/375/768/1280px; teclado, foco, tema claro/oscuro y movimiento reducido.
8. Validación manual con capturas de las pantallas principales antes del despliegue.

**Nota:** las pruebas unitarias y CI no sustituyen una revisión visual/E2E en navegador autenticado.
