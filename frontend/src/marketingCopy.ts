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
      product: "Qué hace",
      outcomes: "Cómo te ayuda",
      integrations: "Integraciones",
      pricing: "Precios",
      login: "Iniciar sesión",
      start: "Crear cuenta",
    },
    hero: {
      eyebrow: "IA para dropshipping y ecommerce",
      titleLead: "Vende más.",
      titleAccent: "Trabaja menos.",
      subtitle:
        "Conecta tus tiendas, WhatsApp, pedidos y clientes. Pregunta qué está pasando, automatiza tareas repetitivas y controla tu negocio desde un solo lugar.",
      primary: "Crear mi cuenta",
      secondary: "Ver cómo funciona",
      note: "Conecta tu primera tienda y empieza a ver tu negocio en minutos.",
      trust: ["Shopify y tus canales", "WhatsApp con IA", "Pedidos bajo control", "Automatizaciones simples", "Rentabilidad por tienda"],
    },
    dashboard: {
      label: "Tu negocio en un vistazo",
      store: "Diaglob Colombia",
      period: "Últimos 30 días",
      revenue: "Ventas",
      profit: "Utilidad",
      delivery: "Tasa de entrega",
      conversations: "Clientes atendidos con IA",
      automation: "Tareas automáticas",
      healthy: "Todo funcionando",
      orders: "Pedidos monitoreados",
    },
    problem: {
      eyebrow: "Deja de apagar incendios",
      title: "Tu negocio no debería depender de diez pestañas y tareas manuales.",
      subtitle:
        "Diaglob reúne lo que pasa en tus tiendas y te ayuda a responder, revisar y actuar sin saltar entre herramientas.",
      items: [
        { title: "Pedidos dispersos", text: "Revisa ventas, pedidos, entregas y productos desde un mismo lugar." },
        { title: "Clientes esperando", text: "Atiende conversaciones con IA que conoce tus productos, políticas y negocio." },
        { title: "Demasiado trabajo manual", text: "Automatiza avisos, seguimientos y tareas que hoy repites todos los días." },
      ],
    },
    outcomes: {
      eyebrow: "Lo que haces más fácil",
      title: "Un negocio más ordenado, rápido y rentable.",
      subtitle: "Diaglob te ayuda a vender y operar mejor sin obligarte a cambiar las herramientas que ya usas.",
      items: [
        { title: "Atiende clientes más rápido", text: "Deja que la IA responda preguntas usando tus productos, políticas y documentos.", proof: "WhatsApp + IA" },
        { title: "Controla todas tus tiendas", text: "Cambia de tienda sin perder el control de pedidos, clientes, productos y resultados.", proof: "Una sola vista" },
        { title: "Sabe dónde ganas y dónde pierdes", text: "Mira utilidad, entregas, cancelaciones y productos para decidir con números reales.", proof: "Ventas + utilidad + entregas" },
      ],
    },
    product: {
      eyebrow: "Tu equipo dentro de Diaglob",
      title: "Todo lo que necesitas para operar sin crecer en caos.",
      subtitle: "Cada parte de Diaglob resuelve una tarea concreta de tu día a día.",
      cards: [
        { title: "Asistente de ventas y soporte", text: "Responde preguntas de clientes con información real de tu negocio.", bullets: ["Usa tu catálogo y tus documentos", "Atiende conversaciones con contexto", "Mantiene la información de cada tienda separada"], tag: "Atención" },
        { title: "Pedidos y productos bajo control", text: "Reúne tu catálogo y tus pedidos para saber qué se vendió y qué necesita atención.", bullets: ["Shopify, Nuvemshop y Dropi", "Pedidos y productos en un solo lugar", "Seguimiento del estado de cada pedido"], tag: "Ventas" },
        { title: "Tu analista de rentabilidad", text: "No te quedes solo con ventas. Descubre qué productos y tiendas realmente te dejan dinero.", bullets: ["Utilidad real", "Entregas y cancelaciones", "Productos que sí dejan margen"], tag: "Rentabilidad" },
        { title: "Automatiza tareas sin programar", text: "Crea procesos paso a paso para que Diaglob se encargue del trabajo repetitivo.", bullets: ["Arrastra y conecta pasos", "Pide ayuda al Copiloto", "Revisa qué pasó en cada ejecución"], tag: "Automatización" },
        { title: "Centro de control de tus tiendas", text: "Detecta rápido qué necesita tu atención sin revisar cada herramienta por separado.", bullets: ["Alertas cuando algo falla", "Estado de tus conexiones", "Vista por tienda o país"], tag: "Control" },
        { title: "Copiloto para tu negocio", text: "Pregúntale qué pasó hoy y pídele ayuda para revisar o automatizar tareas.", bullets: ["Consulta pedidos, clientes y productos", "Te ayuda a crear automatizaciones", "Solo hace lo que tú le permites"], tag: "Copiloto" },
      ],
    },
    integrations: {
      eyebrow: "Sigue usando lo que ya conoces",
      title: "Conecta tus herramientas. Diaglob las pone a trabajar juntas.",
      subtitle: "Shopify, WhatsApp, Google y otras conexiones se organizan alrededor de cada tienda para que no tengas que manejar todo por separado.",
      note: "La disponibilidad de algunas conexiones puede depender del país, proveedor y configuración de tu cuenta.",
    },
    workflow: {
      eyebrow: "Empieza sin complicarte",
      title: "Conecta tu tienda y deja que Diaglob te ayude con el resto.",
      subtitle: "No necesitas configurar todo el primer día. Empieza con una tienda y agrega más cuando lo necesites.",
      steps: [
        { title: "Agrega tu tienda", text: "Conecta Shopify o crea la tienda que quieres manejar desde Diaglob." },
        { title: "Conecta donde vendes y atiendes", text: "Añade WhatsApp, tus documentos y las herramientas que ya usas en el negocio." },
        { title: "Dile a Diaglob qué quieres mejorar", text: "Pregunta por tu negocio, automatiza tareas y revisa qué te está dejando más dinero." },
      ],
    },
    pricing: {
      eyebrow: "Planes simples para empezar",
      title: "Empieza desde US$19 al mes y escala cuando lo necesites.",
      subtitle: "Elige según cuántas tiendas manejas y cuánto usas la IA. Todo lo esencial para operar viene incluido.",
      perMonth: "USD / mes",
      stores: "tiendas",
      store: "tienda",
      includedAi: "respuestas con IA / mes",
      extraAi: "¿Necesitas más respuestas con IA? Agrega 1.000 por US$5 sin cambiar de plan.",
      cta: "Empezar",
      recommended: "Más popular",
      footer: "También hay períodos de 3, 6 y 12 meses con ahorro disponible dentro de Diaglob.",
    },
    faq: {
      eyebrow: "Preguntas frecuentes",
      title: "Lo importante antes de empezar.",
      items: [
        { q: "¿Diaglob reemplaza Shopify o Dropi?", a: "No. Diaglob se conecta con las herramientas que ya usas para ayudarte a manejar tiendas, pedidos, clientes y automatizaciones desde un solo lugar." },
        { q: "¿Puedo manejar tiendas de varios países?", a: "Sí. Diaglob está diseñado como multi-tienda y multi-país, con contexto de moneda, operación e integraciones por tienda." },
        { q: "¿La IA puede usar mis propios documentos?", a: "Sí. Puedes conectar Drive, Sheets y Docs para que la IA responda usando información real de tu negocio." },
        { q: "¿Qué pasa si consumo toda la IA de mi plan?", a: "Puedes comprar paquetes adicionales de respuestas IA. El saldo comprado se mantiene hasta consumirse y se usa después de la cuota incluida del mes." },
        { q: "¿Puedo medir rentabilidad y no solo ventas?", a: "Sí. Puedes ver utilidad, entregas, cancelaciones y desempeño de productos para entender qué realmente deja margen." },
      ],
    },
    final: {
      eyebrow: "Menos tareas. Más control.",
      title: "Haz crecer tus tiendas sin convertir la operación en un caos.",
      subtitle: "Vende, atiende, automatiza y entiende tu rentabilidad desde un solo lugar.",
      cta: "Crear mi cuenta",
      login: "Ya tengo una cuenta",
    },
    footer: {
      tagline: "Vende y opera tus tiendas con más control y menos trabajo manual.",
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
      loginSubtitle: "Entra para revisar tiendas, pedidos, clientes, automatizaciones y resultados.",
      registerEyebrow: "Empieza a operar mejor",
      registerTitle: "Empieza a vender y operar con más control.",
      registerSubtitle: "Crea tu cuenta y conecta las herramientas que ya usas en tu negocio.",
      proofTitle: "Desde un solo lugar puedes:",
      proofItems: ["Controlar varias tiendas y países", "Atender clientes con IA usando tu información", "Automatizar tareas repetitivas", "Ver ventas, utilidad y entregas"],
      backToProduct: "Volver a conocer Diaglob",
    },
  },
  en: {
    nav: { product: "Product", outcomes: "How it helps", integrations: "Integrations", pricing: "Pricing", login: "Log in", start: "Create account" },
    hero: {
      eyebrow: "AI for dropshipping and ecommerce",
      titleLead: "Sell more.",
      titleAccent: "Work less.",
      subtitle: "Connect your stores, WhatsApp, orders and customers. Ask what is happening, automate repetitive work and control your business from one place.",
      primary: "Create my account",
      secondary: "See how it works",
      note: "Connect your first store and start seeing your business in minutes.",
      trust: ["Shopify and your channels", "WhatsApp with AI", "Orders under control", "Simple automations", "Profit by store"],
    },
    dashboard: { label: "Your business at a glance", store: "Diaglob Colombia", period: "Last 30 days", revenue: "Sales", profit: "Profit", delivery: "Delivery rate", conversations: "Customers helped by AI", automation: "Automatic tasks", healthy: "Everything running", orders: "Orders monitored" },
    problem: {
      eyebrow: "Stop putting out fires",
      title: "Your business should not depend on ten tabs and manual tasks.",
      subtitle: "Diaglob brings your stores together and helps you answer, review and act without jumping between tools.",
      items: [
        { title: "Orders everywhere", text: "Review sales, orders, deliveries and products from one place." },
        { title: "Customers waiting", text: "Answer conversations with AI that knows your products, policies and business." },
        { title: "Too much repetitive work", text: "Automate alerts, follow-ups and tasks you repeat every day." },
      ],
    },
    outcomes: {
      eyebrow: "What gets easier",
      title: "A more organized, faster and more profitable business.",
      subtitle: "Diaglob helps you sell and operate better without forcing you to replace the tools you already use.",
      items: [
        { title: "Help customers faster", text: "Let AI answer questions using your products, policies and documents.", proof: "WhatsApp + AI" },
        { title: "Control all your stores", text: "Switch stores without losing track of orders, customers, products and results.", proof: "One view" },
        { title: "Know where you make and lose money", text: "See profit, deliveries, cancellations and products using real numbers.", proof: "Sales + profit + delivery" },
      ],
    },
    product: {
      eyebrow: "Your team inside Diaglob",
      title: "Everything you need to operate without growing the chaos.",
      subtitle: "Every part of Diaglob solves a concrete task in your day-to-day business.",
      cards: [
        { title: "Sales and support assistant", text: "Answer customer questions using real information from your business.", bullets: ["Uses your catalog and documents", "Keeps context in conversations", "Keeps each store separated"], tag: "Support" },
        { title: "Orders and products under control", text: "Bring your catalog and orders together so you know what sold and what needs attention.", bullets: ["Shopify, Nuvemshop and Dropi", "Orders and products in one place", "Follow each order status"], tag: "Sales" },
        { title: "Your profitability analyst", text: "Go beyond revenue and see which products and stores actually make money.", bullets: ["Real profit", "Deliveries and cancellations", "Products that keep margin"], tag: "Profit" },
        { title: "Automate tasks without coding", text: "Build step-by-step processes so Diaglob handles repetitive work for you.", bullets: ["Drag and connect steps", "Ask Copilot for help", "See what happened in every run"], tag: "Automation" },
        { title: "Control center for your stores", text: "Spot what needs attention without checking every tool separately.", bullets: ["Alerts when something fails", "Connection status", "View by store or country"], tag: "Control" },
        { title: "Copilot for your business", text: "Ask what happened today and get help reviewing or automating work.", bullets: ["Checks orders, customers and products", "Helps create automations", "Only does what you allow"], tag: "Copilot" },
      ],
    },
    integrations: { eyebrow: "Keep using what you already know", title: "Connect your tools. Diaglob makes them work together.", subtitle: "Shopify, WhatsApp, Google and other connections are organized around each store so you do not have to manage everything separately.", note: "Some connections depend on country, provider and account configuration." },
    workflow: {
      eyebrow: "Start without the complexity", title: "Connect your store and let Diaglob help with the rest.", subtitle: "You do not need to configure everything on day one. Start with one store and add more when you need them.",
      steps: [
        { title: "Add your store", text: "Connect Shopify or create the store you want to manage in Diaglob." },
        { title: "Connect where you sell and support customers", text: "Add WhatsApp, your documents and the tools you already use." },
        { title: "Tell Diaglob what you want to improve", text: "Ask about your business, automate tasks and see what is making you more money." },
      ],
    },
    pricing: { eyebrow: "Simple plans to get started", title: "Start at US$19/month and scale when you need to.", subtitle: "Choose based on the number of stores you run and how much AI you use. The essentials to operate are included.", perMonth: "USD / month", stores: "stores", store: "store", includedAi: "AI answers / month", extraAi: "Need more AI answers? Add 1,000 for US$5 without changing your plan.", cta: "Get started", recommended: "Most popular", footer: "3, 6 and 12-month billing periods with savings are also available inside Diaglob." },
    faq: {
      eyebrow: "FAQ", title: "What matters before you start.",
      items: [
        { q: "Does Diaglob replace Shopify or Dropi?", a: "No. Diaglob connects to the tools you already use and helps you manage stores, orders, customers and automations from one place." },
        { q: "Can I manage stores in multiple countries?", a: "Yes. Diaglob is designed for multi-store, multi-country operations with currency, operational context and integrations per store." },
        { q: "Can AI use my own documents?", a: "Yes. Connect Drive, Sheets and Docs so AI can answer using real information from your business." },
        { q: "What happens when I use all AI included in my plan?", a: "You can buy additional AI response packages. Purchased balance remains available until consumed and is used after the monthly included allowance." },
        { q: "Can I measure profitability, not just sales?", a: "Yes. You can see profit, deliveries, cancellations and product performance to understand what really creates margin." },
      ],
    },
    final: { eyebrow: "Less busywork. More control.", title: "Grow your stores without turning operations into chaos.", subtitle: "Sell, support customers, automate work and understand your profitability from one place.", cta: "Create my account", login: "I already have an account" },
    footer: { tagline: "Sell and run your stores with more control and less manual work.", product: "Product", legal: "Legal", account: "Account", privacy: "Privacy", terms: "Terms", rights: "All rights reserved." },
    auth: {
      loginEyebrow: "Your operation is waiting", loginTitle: "Get everything back under control.", loginSubtitle: "Sign in to review stores, orders, customers, automations and results.", registerEyebrow: "Start operating better", registerTitle: "Start selling and operating with more control.", registerSubtitle: "Create your account and connect the tools you already use in your business.", proofTitle: "From one place you can:", proofItems: ["Control multiple stores and countries", "Help customers with AI using your information", "Automate repetitive tasks", "See sales, profit and deliveries"], backToProduct: "Back to Diaglob",
    },
  },
  "pt-BR": {
    nav: { product: "Produto", outcomes: "Resultados", integrations: "Integrações", pricing: "Preços", login: "Entrar", start: "Criar conta" },
    hero: {
      eyebrow: "IA para dropshipping e ecommerce",
      titleLead: "Venda mais.",
      titleAccent: "Trabalhe menos.",
      subtitle: "Conecte suas lojas, WhatsApp, pedidos e clientes. Pergunte o que está acontecendo, automatize tarefas repetitivas e controle o negócio em um só lugar.",
      primary: "Criar minha conta",
      secondary: "Ver como funciona",
      note: "Conecte sua primeira loja e comece a enxergar seu negócio em minutos.",
      trust: ["Shopify e seus canais", "WhatsApp com IA", "Pedidos sob controle", "Automações simples", "Rentabilidade por loja"],
    },
    dashboard: { label: "Seu negócio em um relance", store: "Diaglob Brasil", period: "Últimos 30 dias", revenue: "Vendas", profit: "Lucro", delivery: "Taxa de entrega", conversations: "Clientes atendidos com IA", automation: "Tarefas automáticas", healthy: "Tudo funcionando", orders: "Pedidos monitorados" },
    problem: {
      eyebrow: "Pare de apagar incêndios", title: "Seu negócio não deveria depender de dez abas e tarefas manuais.", subtitle: "Diaglob reúne o que acontece nas suas lojas e ajuda você a responder, revisar e agir sem pular entre ferramentas.",
      items: [
        { title: "Pedidos espalhados", text: "Revise vendas, pedidos, entregas e produtos em um só lugar." },
        { title: "Clientes esperando", text: "Atenda conversas com IA que conhece seus produtos, políticas e negócio." },
        { title: "Trabalho repetitivo demais", text: "Automatize alertas, acompanhamentos e tarefas que você repete todos os dias." },
      ],
    },
    outcomes: {
      eyebrow: "O que fica mais fácil", title: "Um negócio mais organizado, rápido e rentável.", subtitle: "Diaglob ajuda você a vender e operar melhor sem obrigar a trocar as ferramentas que já usa.",
      items: [
        { title: "Atenda clientes mais rápido", text: "Deixe a IA responder perguntas usando seus produtos, políticas e documentos.", proof: "WhatsApp + IA" },
        { title: "Controle todas as suas lojas", text: "Troque de loja sem perder o controle de pedidos, clientes, produtos e resultados.", proof: "Uma visão" },
        { title: "Saiba onde ganha e onde perde dinheiro", text: "Veja lucro, entregas, cancelamentos e produtos usando números reais.", proof: "Vendas + lucro + entregas" },
      ],
    },
    product: {
      eyebrow: "Seu time dentro do Diaglob", title: "Tudo que você precisa para operar sem aumentar o caos.", subtitle: "Cada parte do Diaglob resolve uma tarefa concreta do seu dia a dia.",
      cards: [
        { title: "Assistente de vendas e suporte", text: "Responda perguntas de clientes usando informações reais do seu negócio.", bullets: ["Usa seu catálogo e documentos", "Mantém contexto nas conversas", "Mantém cada loja separada"], tag: "Atendimento" },
        { title: "Pedidos e produtos sob controle", text: "Reúna catálogo e pedidos para saber o que vendeu e o que precisa de atenção.", bullets: ["Shopify, Nuvemshop e Dropi", "Pedidos e produtos em um só lugar", "Acompanhe o status de cada pedido"], tag: "Vendas" },
        { title: "Seu analista de rentabilidade", text: "Vá além das vendas e veja quais produtos e lojas realmente deixam dinheiro.", bullets: ["Lucro real", "Entregas e cancelamentos", "Produtos que preservam margem"], tag: "Rentabilidade" },
        { title: "Automatize tarefas sem programar", text: "Crie processos passo a passo para o Diaglob cuidar do trabalho repetitivo.", bullets: ["Arraste e conecte passos", "Peça ajuda ao Copiloto", "Veja o que aconteceu em cada execução"], tag: "Automação" },
        { title: "Centro de controle das suas lojas", text: "Encontre rápido o que precisa de atenção sem abrir cada ferramenta separadamente.", bullets: ["Alertas quando algo falha", "Estado das conexões", "Visão por loja ou país"], tag: "Controle" },
        { title: "Copiloto para o seu negócio", text: "Pergunte o que aconteceu hoje e peça ajuda para revisar ou automatizar tarefas.", bullets: ["Consulta pedidos, clientes e produtos", "Ajuda a criar automações", "Só faz o que você permite"], tag: "Copiloto" },
      ],
    },
    integrations: { eyebrow: "Continue usando o que você já conhece", title: "Conecte suas ferramentas. Diaglob faz elas trabalharem juntas.", subtitle: "Shopify, WhatsApp, Google e outras conexões ficam organizadas por loja para você não precisar gerenciar tudo separadamente.", note: "Algumas conexões dependem do país, provedor e configuração da conta." },
    workflow: {
      eyebrow: "Comece sem complicação", title: "Conecte sua loja e deixe o Diaglob ajudar com o resto.", subtitle: "Você não precisa configurar tudo no primeiro dia. Comece com uma loja e adicione mais quando precisar.",
      steps: [
        { title: "Adicione sua loja", text: "Conecte Shopify ou crie a loja que você quer gerenciar no Diaglob." },
        { title: "Conecte onde você vende e atende", text: "Adicione WhatsApp, seus documentos e as ferramentas que já usa no negócio." },
        { title: "Diga ao Diaglob o que quer melhorar", text: "Pergunte sobre seu negócio, automatize tarefas e veja o que está deixando mais dinheiro." },
      ],
    },
    pricing: { eyebrow: "Planos simples para começar", title: "Comece por US$19/mês e escale quando precisar.", subtitle: "Escolha de acordo com quantas lojas você gerencia e quanto usa a IA. O essencial para operar está incluído.", perMonth: "USD / mês", stores: "lojas", store: "loja", includedAi: "respostas com IA / mês", extraAi: "Precisa de mais respostas com IA? Adicione 1.000 por US$5 sem trocar de plano.", cta: "Começar", recommended: "Mais popular", footer: "Também há períodos de 3, 6 e 12 meses com economia dentro do Diaglob." },
    faq: {
      eyebrow: "Perguntas frequentes", title: "O que importa antes de começar.",
      items: [
        { q: "Diaglob substitui Shopify ou Dropi?", a: "Não. Diaglob se conecta às ferramentas que você já usa e ajuda a gerenciar lojas, pedidos, clientes e automações em um só lugar." },
        { q: "Posso gerenciar lojas em vários países?", a: "Sim. Diaglob foi projetado para operações multi-loja e multi-país, com moeda, contexto e integrações por loja." },
        { q: "A IA pode usar meus próprios documentos?", a: "Sim. Conecte Drive, Sheets e Docs para a IA responder usando informações reais do seu negócio." },
        { q: "O que acontece quando termino a IA incluída?", a: "Você pode comprar pacotes adicionais. O saldo comprado continua disponível até ser consumido e é usado depois da franquia mensal." },
        { q: "Posso medir rentabilidade e não apenas vendas?", a: "Sim. Você pode ver lucro, entregas, cancelamentos e desempenho dos produtos para entender o que realmente gera margem." },
      ],
    },
    final: { eyebrow: "Menos tarefas. Mais controle.", title: "Faça suas lojas crescerem sem transformar a operação em caos.", subtitle: "Venda, atenda, automatize e entenda sua rentabilidade em um só lugar.", cta: "Criar minha conta", login: "Já tenho uma conta" },
    footer: { tagline: "Venda e opere suas lojas com mais controle e menos trabalho manual.", product: "Produto", legal: "Legal", account: "Conta", privacy: "Privacidade", terms: "Termos", rights: "Todos os direitos reservados." },
    auth: {
      loginEyebrow: "Sua operação está esperando", loginTitle: "Volte a ter tudo sob controle.", loginSubtitle: "Entre para revisar lojas, pedidos, clientes, automações e resultados.", registerEyebrow: "Comece a operar melhor", registerTitle: "Comece a vender e operar com mais controle.", registerSubtitle: "Crie sua conta e conecte as ferramentas que já usa no seu negócio.", proofTitle: "De um só lugar você pode:", proofItems: ["Controlar várias lojas e países", "Atender clientes com IA usando suas informações", "Automatizar tarefas repetitivas", "Ver vendas, lucro e entregas"], backToProduct: "Voltar ao Diaglob",
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
