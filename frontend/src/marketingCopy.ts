export type MarketingLocale = "es" | "en" | "pt-BR";

export type MarketingCopy = {
  nav: {
    product: string;
    outcomes: string;
    integrations: string;
    pricing: string;
    login: string;
    start: string;
  };
  hero: {
    eyebrow: string;
    titleLead: string;
    titleAccent: string;
    subtitle: string;
    primary: string;
    secondary: string;
    note: string;
    trust: string[];
  };
  dashboard: {
    label: string;
    store: string;
    period: string;
    revenue: string;
    profit: string;
    delivery: string;
    conversations: string;
    automation: string;
    healthy: string;
    orders: string;
  };
  problem: {
    eyebrow: string;
    title: string;
    subtitle: string;
    items: Array<{ title: string; text: string }>;
  };
  outcomes: {
    eyebrow: string;
    title: string;
    subtitle: string;
    items: Array<{ title: string; text: string; proof: string }>;
  };
  product: {
    eyebrow: string;
    title: string;
    subtitle: string;
    cards: Array<{ title: string; text: string; bullets: string[]; tag: string }>;
  };
  integrations: {
    eyebrow: string;
    title: string;
    subtitle: string;
    note: string;
  };
  workflow: {
    eyebrow: string;
    title: string;
    subtitle: string;
    steps: Array<{ title: string; text: string }>;
  };
  pricing: {
    eyebrow: string;
    title: string;
    subtitle: string;
    perMonth: string;
    stores: string;
    store: string;
    includedAi: string;
    extraAi: string;
    cta: string;
    recommended: string;
    footer: string;
  };
  faq: {
    eyebrow: string;
    title: string;
    items: Array<{ q: string; a: string }>;
  };
  final: {
    eyebrow: string;
    title: string;
    subtitle: string;
    cta: string;
    login: string;
  };
  footer: {
    tagline: string;
    product: string;
    legal: string;
    account: string;
    privacy: string;
    terms: string;
    rights: string;
  };
  auth: {
    loginEyebrow: string;
    loginTitle: string;
    loginSubtitle: string;
    registerEyebrow: string;
    registerTitle: string;
    registerSubtitle: string;
    proofTitle: string;
    proofItems: string[];
    backToProduct: string;
  };
};

const copy: Record<MarketingLocale, MarketingCopy> = {
  es: {
    nav: {
      product: "Producto",
      outcomes: "Resultados",
      integrations: "Integraciones",
      pricing: "Precios",
      login: "Iniciar sesión",
      start: "Crear cuenta",
    },
    hero: {
      eyebrow: "El sistema operativo para dropshipping",
      titleLead: "Escala tu operación.",
      titleAccent: "No el caos.",
      subtitle:
        "Centraliza tiendas, conversaciones, pedidos, automatizaciones, conocimiento y analítica en una sola plataforma diseñada para operar dropshipping en serio.",
      primary: "Empezar con Diaglob",
      secondary: "Ver cómo funciona",
      note: "Configura tu workspace y conecta tu primera tienda en minutos.",
      trust: ["Multi-tienda", "Multi-país", "IA con tu conocimiento", "Automatizaciones", "Analítica de dropshipping"],
    },
    dashboard: {
      label: "Vista de operación",
      store: "Diaglob Colombia",
      period: "Últimos 30 días",
      revenue: "Ventas",
      profit: "Utilidad",
      delivery: "Tasa de entrega",
      conversations: "Conversaciones IA",
      automation: "Automatizaciones activas",
      healthy: "Operación saludable",
      orders: "Pedidos monitoreados",
    },
    problem: {
      eyebrow: "Menos herramientas. Más control.",
      title: "Tu margen se pierde cuando la operación vive en diez pestañas.",
      subtitle:
        "Diaglob conecta los puntos que normalmente manejas por separado para que puedas tomar decisiones y ejecutar desde un solo lugar.",
      items: [
        { title: "Datos fragmentados", text: "Ventas, costos, pedidos y conversaciones dejan de vivir en sistemas aislados." },
        { title: "Trabajo manual", text: "Reduce tareas repetitivas con flujos y automatizaciones que reaccionan a tu operación." },
        { title: "Decisiones a ciegas", text: "Mide utilidad, entregas, cancelaciones y productos para actuar con contexto real." },
      ],
    },
    outcomes: {
      eyebrow: "Lo que cambia en tu día a día",
      title: "Una operación que responde, vende y aprende contigo.",
      subtitle: "Cada módulo está pensado para quitar fricción a una parte concreta del negocio.",
      items: [
        { title: "Atiende más sin perder contexto", text: "Unifica conversaciones y deja que agentes de IA respondan usando información real de tu negocio.", proof: "WhatsApp + Telegram + Knowledge" },
        { title: "Opera varias tiendas como una sola empresa", text: "Separa país, moneda, catálogo y conexiones por tienda sin perder una vista central.", proof: "Multi-store + Multi-country" },
        { title: "Protege el margen", text: "Ve rentabilidad, desempeño de pedidos y productos con métricas pensadas para dropshipping.", proof: "Profitability + Delivery analytics" },
      ],
    },
    product: {
      eyebrow: "Todo lo que ya tienes dentro de Diaglob",
      title: "De conversación a pedido, de pedido a decisión.",
      subtitle: "Una plataforma modular para operar el ciclo completo, sin obligarte a cambiar todo tu stack de un día para otro.",
      cards: [
        { title: "Agentes de IA con tu conocimiento", text: "Conecta Google Drive, Sheets y Docs para responder con información de productos, políticas, operación y documentos reales.", bullets: ["Knowledge bases", "Respuestas contextualizadas", "Consumo IA medido"], tag: "AI + RAG" },
        { title: "Comercio conectado", text: "Sincroniza catálogo y operación comercial con los canales que ya utilizas.", bullets: ["Shopify", "Nuvemshop", "Dropi", "Pedidos y productos"], tag: "Commerce" },
        { title: "Analítica para dropshippers", text: "No te quedes solo con ventas. Sigue utilidad, tasas de entrega, cancelaciones, retornos y productos que realmente funcionan.", bullets: ["Rentabilidad", "Pedidos", "Productos", "Comparación por período"], tag: "Analytics" },
        { title: "Automatizaciones visuales", text: "Crea flujos para mover la operación sin depender de tareas manuales repetitivas.", bullets: ["Triggers y acciones", "Versionado de flujos", "Ejecuciones y simulación"], tag: "Automation" },
        { title: "Centro de operaciones", text: "Monitorea integraciones, conversaciones, pedidos, productos, agentes y alertas desde una vista consolidada.", bullets: ["Estado de integraciones", "Alertas operativas", "Resumen por tienda"], tag: "Operations" },
        { title: "Uso de IA que escala contigo", text: "Cada plan incluye capacidad mensual y puedes comprar respuestas adicionales sin cambiar de plan cuando tengas un pico de demanda.", bullets: ["Saldo extra persistente", "Compra por paquetes", "Uso incluido primero"], tag: "AI usage" },
      ],
    },
    integrations: {
      eyebrow: "Conecta tu stack",
      title: "Diaglob no te obliga a empezar de cero.",
      subtitle: "Conecta ventas, mensajería, conocimiento, publicidad y pagos alrededor de cada tienda.",
      note: "La disponibilidad de algunas conexiones puede depender del país, proveedor y configuración de tu cuenta.",
    },
    workflow: {
      eyebrow: "Cómo empieza",
      title: "De cero a operación conectada en tres pasos.",
      subtitle: "Empieza pequeño y conecta más piezas conforme crece tu negocio.",
      steps: [
        { title: "Crea tu organización y tiendas", text: "Define cada operación por país, moneda y contexto comercial." },
        { title: "Conecta tus canales", text: "Añade comercio, mensajería, Google Knowledge, pagos y datos publicitarios." },
        { title: "Automatiza y mide", text: "Activa agentes, flujos y analítica para operar con menos trabajo manual y mejores decisiones." },
      ],
    },
    pricing: {
      eyebrow: "Precios que crecen contigo",
      title: "Empieza con lo que necesitas. Escala cuando tenga sentido.",
      subtitle: "Todos los planes están pensados para una operación real; la diferencia está en capacidad y número de tiendas.",
      perMonth: "USD / mes",
      stores: "tiendas",
      store: "tienda",
      includedAi: "respuestas IA incluidas / mes",
      extraAi: "¿Necesitas más IA? Compra 1.000 respuestas extra por US$5 sin cambiar de plan.",
      cta: "Empezar",
      recommended: "Más popular",
      footer: "También hay períodos de 3, 6 y 12 meses con ahorro disponible dentro de Diaglob.",
    },
    faq: {
      eyebrow: "Preguntas frecuentes",
      title: "Lo importante antes de empezar.",
      items: [
        { q: "¿Diaglob reemplaza Shopify o Dropi?", a: "No. Diaglob funciona como capa de operación y automatización alrededor de tus herramientas. Conecta los sistemas que ya utilizas y centraliza la gestión." },
        { q: "¿Puedo manejar tiendas de varios países?", a: "Sí. Diaglob está diseñado como multi-tienda y multi-país, con contexto de moneda, operación e integraciones por tienda." },
        { q: "¿La IA puede usar mis propios documentos?", a: "Sí. Puedes conectar fuentes de Google como Drive, Sheets y Docs para alimentar bases de conocimiento y dar contexto a los agentes." },
        { q: "¿Qué pasa si consumo toda la IA de mi plan?", a: "Puedes comprar paquetes adicionales de respuestas IA. El saldo comprado se mantiene hasta consumirse y se usa después de la cuota incluida del mes." },
        { q: "¿Puedo medir rentabilidad y no solo ventas?", a: "Sí. La analítica de dropshipping incluye métricas de rentabilidad y desempeño operativo para entender qué realmente deja margen." },
      ],
    },
    final: {
      eyebrow: "Tu siguiente etapa no necesita más caos",
      title: "Construye una operación que pueda crecer sin romperse.",
      subtitle: "Centraliza, automatiza y mide tu negocio de dropshipping con una plataforma hecha para esa realidad.",
      cta: "Crear mi cuenta",
      login: "Ya tengo una cuenta",
    },
    footer: {
      tagline: "Operación, IA y analítica para ecommerce y dropshipping.",
      product: "Producto",
      legal: "Legal",
      account: "Cuenta",
      privacy: "Privacidad",
      terms: "Términos",
      rights: "Todos los derechos reservados.",
    },
    auth: {
      loginEyebrow: "Tu operación te espera",
      loginTitle: "Vuelve a tener todo bajo control.",
      loginSubtitle: "Entra a tu workspace para gestionar tiendas, conversaciones, automatizaciones y analítica.",
      registerEyebrow: "Empieza a operar mejor",
      registerTitle: "Crea la base para escalar sin perder control.",
      registerSubtitle: "Abre tu workspace y conecta progresivamente las herramientas que ya usas en tu negocio.",
      proofTitle: "Desde un solo lugar puedes:",
      proofItems: ["Gestionar varias tiendas y países", "Conectar IA a tu propio conocimiento", "Automatizar tareas y conversaciones", "Medir rentabilidad y desempeño operativo"],
      backToProduct: "Volver a conocer Diaglob",
    },
  },
  en: {
    nav: { product: "Product", outcomes: "Outcomes", integrations: "Integrations", pricing: "Pricing", login: "Log in", start: "Create account" },
    hero: {
      eyebrow: "The operating system for dropshipping",
      titleLead: "Scale your operation.",
      titleAccent: "Not the chaos.",
      subtitle: "Centralize stores, conversations, orders, automations, knowledge and analytics in one platform built for serious dropshipping operations.",
      primary: "Start with Diaglob",
      secondary: "See how it works",
      note: "Set up your workspace and connect your first store in minutes.",
      trust: ["Multi-store", "Multi-country", "AI with your knowledge", "Automations", "Dropshipping analytics"],
    },
    dashboard: { label: "Operations view", store: "Diaglob Colombia", period: "Last 30 days", revenue: "Sales", profit: "Profit", delivery: "Delivery rate", conversations: "AI conversations", automation: "Active automations", healthy: "Healthy operation", orders: "Orders monitored" },
    problem: {
      eyebrow: "Fewer tools. More control.",
      title: "Margin disappears when your operation lives across ten tabs.",
      subtitle: "Diaglob connects the pieces you usually manage separately so you can decide and execute from one place.",
      items: [
        { title: "Fragmented data", text: "Sales, costs, orders and conversations stop living in disconnected systems." },
        { title: "Manual work", text: "Reduce repetitive work with flows and automations that react to your operation." },
        { title: "Blind decisions", text: "Track profit, deliveries, cancellations and products with real operational context." },
      ],
    },
    outcomes: {
      eyebrow: "What changes day to day",
      title: "An operation that responds, sells and learns with you.",
      subtitle: "Every module removes friction from a concrete part of the business.",
      items: [
        { title: "Serve more customers without losing context", text: "Unify conversations and let AI agents answer using real business knowledge.", proof: "WhatsApp + Telegram + Knowledge" },
        { title: "Run multiple stores like one company", text: "Separate country, currency, catalog and connections per store while keeping a central view.", proof: "Multi-store + Multi-country" },
        { title: "Protect your margin", text: "See profitability, order performance and products through metrics designed for dropshipping.", proof: "Profitability + Delivery analytics" },
      ],
    },
    product: {
      eyebrow: "Everything already inside Diaglob",
      title: "From conversation to order, from order to decision.",
      subtitle: "A modular platform for the full operating cycle without forcing you to replace your entire stack overnight.",
      cards: [
        { title: "AI agents with your knowledge", text: "Connect Google Drive, Sheets and Docs so agents answer with real product, policy and operational information.", bullets: ["Knowledge bases", "Context-aware answers", "Metered AI usage"], tag: "AI + RAG" },
        { title: "Connected commerce", text: "Sync catalog and commerce operations with the channels you already use.", bullets: ["Shopify", "Nuvemshop", "Dropi", "Orders and products"], tag: "Commerce" },
        { title: "Analytics for dropshippers", text: "Go beyond revenue. Track profit, delivery rates, cancellations, returns and products that actually work.", bullets: ["Profitability", "Orders", "Products", "Period comparison"], tag: "Analytics" },
        { title: "Visual automations", text: "Build flows that move work forward without repetitive manual tasks.", bullets: ["Triggers and actions", "Flow versioning", "Runs and simulation"], tag: "Automation" },
        { title: "Operations center", text: "Monitor integrations, conversations, orders, products, agents and alerts from one consolidated view.", bullets: ["Integration health", "Operational alerts", "Per-store summary"], tag: "Operations" },
        { title: "AI usage that scales with you", text: "Every plan includes monthly capacity and you can buy extra responses without changing plans during demand spikes.", bullets: ["Persistent extra balance", "One-time packages", "Included usage first"], tag: "AI usage" },
      ],
    },
    integrations: { eyebrow: "Connect your stack", title: "Diaglob does not force you to start over.", subtitle: "Connect commerce, messaging, knowledge, advertising and payments around each store.", note: "Some connections depend on country, provider and account configuration." },
    workflow: {
      eyebrow: "How it starts", title: "From zero to connected operations in three steps.", subtitle: "Start small and connect more as your business grows.",
      steps: [
        { title: "Create your organization and stores", text: "Define each operation by country, currency and commercial context." },
        { title: "Connect your channels", text: "Add commerce, messaging, Google Knowledge, payments and advertising data." },
        { title: "Automate and measure", text: "Turn on agents, flows and analytics to reduce manual work and make better decisions." },
      ],
    },
    pricing: { eyebrow: "Pricing that grows with you", title: "Start with what you need. Scale when it makes sense.", subtitle: "Every plan is built for real operations; capacity and number of stores are what change.", perMonth: "USD / month", stores: "stores", store: "store", includedAi: "included AI responses / month", extraAi: "Need more AI? Buy 1,000 extra responses for US$5 without changing your plan.", cta: "Get started", recommended: "Most popular", footer: "3, 6 and 12-month billing periods with savings are also available inside Diaglob." },
    faq: {
      eyebrow: "FAQ", title: "What matters before you start.",
      items: [
        { q: "Does Diaglob replace Shopify or Dropi?", a: "No. Diaglob is an operations and automation layer around your existing tools. It connects the systems you already use and centralizes management." },
        { q: "Can I manage stores in multiple countries?", a: "Yes. Diaglob is designed for multi-store, multi-country operations with currency, operational context and integrations per store." },
        { q: "Can AI use my own documents?", a: "Yes. Connect Google sources such as Drive, Sheets and Docs to feed knowledge bases and give agents business context." },
        { q: "What happens when I use all AI included in my plan?", a: "You can buy additional AI response packages. Purchased balance remains available until consumed and is used after the monthly included allowance." },
        { q: "Can I measure profitability, not just sales?", a: "Yes. Dropshipping analytics includes profitability and operational performance metrics so you can understand what really produces margin." },
      ],
    },
    final: { eyebrow: "Your next stage does not need more chaos", title: "Build an operation that can grow without breaking.", subtitle: "Centralize, automate and measure your dropshipping business with a platform built for that reality.", cta: "Create my account", login: "I already have an account" },
    footer: { tagline: "Operations, AI and analytics for ecommerce and dropshipping.", product: "Product", legal: "Legal", account: "Account", privacy: "Privacy", terms: "Terms", rights: "All rights reserved." },
    auth: {
      loginEyebrow: "Your operation is waiting", loginTitle: "Get everything back under control.", loginSubtitle: "Enter your workspace to manage stores, conversations, automations and analytics.", registerEyebrow: "Start operating better", registerTitle: "Build the foundation to scale without losing control.", registerSubtitle: "Create your workspace and progressively connect the tools you already use.", proofTitle: "From one place you can:", proofItems: ["Manage multiple stores and countries", "Connect AI to your own knowledge", "Automate tasks and conversations", "Measure profitability and operations"], backToProduct: "Back to Diaglob",
    },
  },
  "pt-BR": {
    nav: { product: "Produto", outcomes: "Resultados", integrations: "Integrações", pricing: "Preços", login: "Entrar", start: "Criar conta" },
    hero: {
      eyebrow: "O sistema operacional para dropshipping",
      titleLead: "Escale sua operação.",
      titleAccent: "Não o caos.",
      subtitle: "Centralize lojas, conversas, pedidos, automações, conhecimento e analytics em uma única plataforma feita para operações sérias de dropshipping.",
      primary: "Começar com Diaglob",
      secondary: "Ver como funciona",
      note: "Configure seu workspace e conecte sua primeira loja em minutos.",
      trust: ["Multi-loja", "Multi-país", "IA com seu conhecimento", "Automações", "Analytics de dropshipping"],
    },
    dashboard: { label: "Visão da operação", store: "Diaglob Brasil", period: "Últimos 30 dias", revenue: "Vendas", profit: "Lucro", delivery: "Taxa de entrega", conversations: "Conversas com IA", automation: "Automações ativas", healthy: "Operação saudável", orders: "Pedidos monitorados" },
    problem: {
      eyebrow: "Menos ferramentas. Mais controle.", title: "Sua margem some quando a operação vive em dez abas.", subtitle: "Diaglob conecta as partes que você normalmente gerencia separadamente para decidir e executar em um só lugar.",
      items: [
        { title: "Dados fragmentados", text: "Vendas, custos, pedidos e conversas deixam de viver em sistemas desconectados." },
        { title: "Trabalho manual", text: "Reduza tarefas repetitivas com fluxos e automações que reagem à operação." },
        { title: "Decisões no escuro", text: "Acompanhe lucro, entregas, cancelamentos e produtos com contexto operacional real." },
      ],
    },
    outcomes: {
      eyebrow: "O que muda no dia a dia", title: "Uma operação que responde, vende e aprende com você.", subtitle: "Cada módulo remove atrito de uma parte concreta do negócio.",
      items: [
        { title: "Atenda mais sem perder contexto", text: "Unifique conversas e deixe agentes de IA responderem usando conhecimento real do negócio.", proof: "WhatsApp + Telegram + Knowledge" },
        { title: "Opere várias lojas como uma empresa", text: "Separe país, moeda, catálogo e conexões por loja mantendo uma visão central.", proof: "Multi-store + Multi-country" },
        { title: "Proteja sua margem", text: "Veja rentabilidade, desempenho dos pedidos e produtos com métricas para dropshipping.", proof: "Profitability + Delivery analytics" },
      ],
    },
    product: {
      eyebrow: "Tudo que já existe dentro do Diaglob", title: "Da conversa ao pedido, do pedido à decisão.", subtitle: "Uma plataforma modular para todo o ciclo operacional sem obrigar você a trocar todo o stack de uma vez.",
      cards: [
        { title: "Agentes de IA com seu conhecimento", text: "Conecte Google Drive, Sheets e Docs para responder com informações reais de produtos, políticas e operação.", bullets: ["Knowledge bases", "Respostas contextualizadas", "Uso de IA medido"], tag: "AI + RAG" },
        { title: "Comércio conectado", text: "Sincronize catálogo e operação comercial com os canais que você já usa.", bullets: ["Shopify", "Nuvemshop", "Dropi", "Pedidos e produtos"], tag: "Commerce" },
        { title: "Analytics para dropshippers", text: "Vá além das vendas. Acompanhe lucro, entrega, cancelamentos, devoluções e produtos que funcionam.", bullets: ["Rentabilidade", "Pedidos", "Produtos", "Comparação por período"], tag: "Analytics" },
        { title: "Automações visuais", text: "Crie fluxos que movem a operação sem depender de tarefas manuais repetitivas.", bullets: ["Triggers e ações", "Versionamento", "Execuções e simulação"], tag: "Automation" },
        { title: "Centro de operações", text: "Monitore integrações, conversas, pedidos, produtos, agentes e alertas em uma visão consolidada.", bullets: ["Saúde das integrações", "Alertas operacionais", "Resumo por loja"], tag: "Operations" },
        { title: "Uso de IA que escala com você", text: "Cada plano inclui capacidade mensal e você pode comprar respostas extras sem mudar de plano.", bullets: ["Saldo extra persistente", "Pacotes avulsos", "Uso incluído primeiro"], tag: "AI usage" },
      ],
    },
    integrations: { eyebrow: "Conecte seu stack", title: "Diaglob não obriga você a começar do zero.", subtitle: "Conecte comércio, mensagens, conhecimento, publicidade e pagamentos em torno de cada loja.", note: "Algumas conexões dependem do país, provedor e configuração da conta." },
    workflow: {
      eyebrow: "Como começa", title: "Do zero à operação conectada em três passos.", subtitle: "Comece pequeno e conecte mais partes conforme o negócio cresce.",
      steps: [
        { title: "Crie sua organização e lojas", text: "Defina cada operação por país, moeda e contexto comercial." },
        { title: "Conecte seus canais", text: "Adicione comércio, mensagens, Google Knowledge, pagamentos e dados de publicidade." },
        { title: "Automatize e meça", text: "Ative agentes, fluxos e analytics para reduzir trabalho manual e decidir melhor." },
      ],
    },
    pricing: { eyebrow: "Preços que crescem com você", title: "Comece com o que precisa. Escale quando fizer sentido.", subtitle: "Todos os planos são feitos para operações reais; capacidade e número de lojas são o que muda.", perMonth: "USD / mês", stores: "lojas", store: "loja", includedAi: "respostas de IA incluídas / mês", extraAi: "Precisa de mais IA? Compre 1.000 respostas extras por US$5 sem trocar de plano.", cta: "Começar", recommended: "Mais popular", footer: "Também há períodos de 3, 6 e 12 meses com economia dentro do Diaglob." },
    faq: {
      eyebrow: "Perguntas frequentes", title: "O que importa antes de começar.",
      items: [
        { q: "Diaglob substitui Shopify ou Dropi?", a: "Não. Diaglob funciona como uma camada de operação e automação sobre suas ferramentas atuais, conectando e centralizando a gestão." },
        { q: "Posso gerenciar lojas em vários países?", a: "Sim. Diaglob foi projetado para operações multi-loja e multi-país, com moeda, contexto e integrações por loja." },
        { q: "A IA pode usar meus próprios documentos?", a: "Sim. Conecte fontes Google como Drive, Sheets e Docs para alimentar bases de conhecimento e dar contexto aos agentes." },
        { q: "O que acontece quando termino a IA incluída?", a: "Você pode comprar pacotes adicionais. O saldo comprado continua disponível até ser consumido e é usado depois da franquia mensal." },
        { q: "Posso medir rentabilidade e não apenas vendas?", a: "Sim. O analytics de dropshipping inclui rentabilidade e desempenho operacional para entender o que realmente gera margem." },
      ],
    },
    final: { eyebrow: "Sua próxima fase não precisa de mais caos", title: "Construa uma operação que possa crescer sem quebrar.", subtitle: "Centralize, automatize e meça seu dropshipping com uma plataforma feita para essa realidade.", cta: "Criar minha conta", login: "Já tenho uma conta" },
    footer: { tagline: "Operação, IA e analytics para ecommerce e dropshipping.", product: "Produto", legal: "Legal", account: "Conta", privacy: "Privacidade", terms: "Termos", rights: "Todos os direitos reservados." },
    auth: {
      loginEyebrow: "Sua operação está esperando", loginTitle: "Volte a ter tudo sob controle.", loginSubtitle: "Entre no workspace para gerenciar lojas, conversas, automações e analytics.", registerEyebrow: "Comece a operar melhor", registerTitle: "Crie a base para escalar sem perder controle.", registerSubtitle: "Abra seu workspace e conecte aos poucos as ferramentas que já usa.", proofTitle: "De um só lugar você pode:", proofItems: ["Gerenciar várias lojas e países", "Conectar IA ao seu próprio conhecimento", "Automatizar tarefas e conversas", "Medir rentabilidade e operação"], backToProduct: "Voltar ao Diaglob",
    },
  },
};

export function resolveMarketingLocale(language: string): MarketingLocale {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

export function getMarketingCopy(language: string): MarketingCopy {
  return copy[resolveMarketingLocale(language)];
}
