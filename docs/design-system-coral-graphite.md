# DIAGLOB — Sistema visual Coral + grafito

Rama de desarrollo: `feat/coral-graphite-design-system-20261117`.

## Arquitectura y alcance
- `frontend/src/brand-tokens.css`: fuente principal de primitivas (coral, grafito, marfil), roles semánticos claro/oscuro, colores operativos, gráficas, nodos y compatibilidad con el CSS anterior.
- `frontend/src/brand-coral.css`: capa final de aplicación visual para navegación, botones, formularios, tablas, dashboards, marketing y editor de automatizaciones.
- `frontend/src/main.tsx`: importa ambas hojas **después** de los estilos existentes para preservar compatibilidad sin cambiar flujos de negocio.
- `frontend/src/components/automation-flows/FlowNode.tsx` y `FlowCanvas.tsx`: colores funcionales tomados de los tokens, no constantes moradas o azules fijas.
- `frontend/tests/brand-tokens.test.ts`: verifica contrastes esenciales y mapeo de nodos.

## Normas de uso
- Coral de marca: `--brand-core` (`#F06B45`); no se usa para textos pequeños blancos.
- CTA: `--brand-action`, `--brand-action-fg`, `--brand-action-hover` (en claro fondo `#B94729` con texto blanco; en oscuro fondo `#F67C5A` con texto grafito).
- Enlaces/acento textual: `--brand-text-accent` (`#B94729` en claro, `#FFA083` en oscuro).
- Superficies y textos: `--bg-*`, `--text-*`, `--border-*`; nunca aplicar el mismo color a todas las series de un gráfico.
- Estado semántico: `--success-*`, `--warning-*`, `--danger-*`, `--info-*`. No comunicar estado solo con color.
- Gráficos: `--chart-1` (coral protagonista), `--chart-2` (jade), `--chart-3` (ámbar), `--chart-4` (ciruela), `--chart-5` (azul informativo).
- Flujos: `--flow-trigger` coral; `--flow-condition` ámbar; `--flow-action` jade; `--flow-wait` neutro; `--flow-ai` ciruela; `--flow-human` azul informativo; `--flow-neutral` grafito.
- Mantener los atributos `data-theme="light"` y `data-theme="dark"` existentes y la preferencia `diaglob-theme`. No agregar persistencia alternativa.

## Accesibilidad
- Texto normal WCAG AA: mínimo 4,5:1; texto grande y controles no textuales: 3:1.
- Los casos de prueba cubren contraste del texto principal, secundario, enlaces de marca, CTA y anillo de foco contra superficies de ambos temas.
- En interacciones: foco visible, navegación por teclado, texto junto a chips/estado, tamaños táctiles adecuados y respeto a `prefers-reduced-motion`.
- Las pruebas automáticas no sustituyen la revisión visual de estados hover, error, disabled, gráficos o cualquier componente nuevo.

## Validación local
```bash
cd frontend
npm ci
npm test
npm run lint
npm run build
```

## Revisión visual antes del merge
1. Entrar en modo claro y oscuro y recargar; confirmar que no hay parpadeos de tema.
2. Revisar sidebar, topbar, overview, cards KPI, tablas, formularios y modales.
3. Revisar analítica: series diferenciables, leyendas, tooltips, grid y contraste.
4. Revisar automatizaciones: paleta, nodos, minimapa, canvas, conexiones, seleccionado, ejecución, error y espera.
5. Revisar marketing y landing en escritorio y móvil.
6. Navegar con teclado, zoom al 200 %, emular movimiento reducido y revisar visualmente focos y estados deshabilitados.
7. No fusionar ni desplegar hasta completar estas comprobaciones y las CI pertinentes.

**Limitación conocida:** el proyecto contiene estilos legacy con colores explícitos. Esta capa concentra la identidad para áreas principales, pero cualquier nueva pantalla debe migrar progresivamente a tokens y probarse en los dos modos.
