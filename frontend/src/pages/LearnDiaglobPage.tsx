import { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  MessageSquareText,
  PackageCheck,
  PlugZap,
  Rocket,
  ShoppingBag,
  Sparkles,
  Workflow,
} from "lucide-react";

import "../learn-diaglob.css";

interface LearnDiaglobPageProps {
  onNavigate: (page: string) => void;
}

type LearningModule = {
  id: string;
  title: string;
  description: string;
  outcome: string;
  page: string;
  action: string;
  icon: typeof Rocket;
  accent: string;
  lessons: string[];
};

const PROGRESS_KEY = "diaglob-learning-progress-v1";

const MODULES: LearningModule[] = [
  {
    id: "start",
    title: "Empieza aquí",
    description: "Conoce la lógica de Diaglob y ubica lo importante sin perderte entre pantallas.",
    outcome: "Terminas sabiendo dónde revisar tu operación y qué hacer después.",
    page: "overview",
    action: "Abrir dashboard",
    icon: Rocket,
    accent: "violet",
    lessons: [
      "Conoce el Centro de Operaciones",
      "Aprende a cambiar de tienda",
      "Identifica qué necesita atención",
    ],
  },
  {
    id: "conversations",
    title: "Atiende clientes",
    description: "Aprende a trabajar con la bandeja de conversaciones, contexto del cliente e IA.",
    outcome: "Podrás responder más rápido sin perder el contexto del pedido o del cliente.",
    page: "conversations",
    action: "Ir a conversaciones",
    icon: MessageSquareText,
    accent: "cyan",
    lessons: [
      "Lee la bandeja y prioriza chats",
      "Entiende el contexto del cliente",
      "Cambia entre atención humana e IA",
    ],
  },
  {
    id: "copilot",
    title: "Usa el Copiloto",
    description: "Aprende qué preguntarle al Copiloto y cómo convertir una respuesta en una acción.",
    outcome: "Sabrás usar Diaglob como asistente operativo, no solo como dashboard.",
    page: "overview",
    action: "Abrir Centro de Operaciones",
    icon: Bot,
    accent: "blue",
    lessons: [
      "Pregunta qué necesita atención hoy",
      "Pide una explicación de la vista actual",
      "Convierte una recomendación en acción",
    ],
  },
  {
    id: "automations",
    title: "Automatiza tareas",
    description: "Crea procesos para dejar de repetir seguimientos, avisos y tareas operativas.",
    outcome: "Terminas entendiendo triggers, acciones, ejecuciones y flujos.",
    page: "automations",
    action: "Ir a automatizaciones",
    icon: Workflow,
    accent: "violet",
    lessons: [
      "Entiende trigger y acción",
      "Usa una plantilla",
      "Revisa una ejecución y su resultado",
    ],
  },
  {
    id: "orders",
    title: "Controla pedidos",
    description: "Aprende a revisar pedidos, novedades y señales que requieren intervención.",
    outcome: "Podrás detectar pedidos que necesitan atención antes de que escalen.",
    page: "commerce",
    action: "Ir a comercio",
    icon: ShoppingBag,
    accent: "amber",
    lessons: [
      "Encuentra un pedido",
      "Revisa su estado operativo",
      "Identifica pedidos que requieren atención",
    ],
  },
  {
    id: "profitability",
    title: "Entiende tus números",
    description: "Pasa de mirar ventas a entender utilidad, entrega y rentabilidad.",
    outcome: "Sabrás qué productos y tiendas realmente están generando margen.",
    page: "analytics",
    action: "Ir a Analytics",
    icon: BarChart3,
    accent: "green",
    lessons: [
      "Lee ventas y utilidad",
      "Revisa tasa de entrega",
      "Identifica qué producto deja margen",
    ],
  },
  {
    id: "integrations",
    title: "Conecta herramientas",
    description: "Aprende a conectar tu stack para que Diaglob reúna la operación en un solo lugar.",
    outcome: "Entenderás qué integraciones están conectadas y cuáles necesitan atención.",
    page: "integrations",
    action: "Ir a integraciones",
    icon: PlugZap,
    accent: "cyan",
    lessons: [
      "Revisa el estado de tus conexiones",
      "Conecta tu ecommerce",
      "Detecta una integración con problemas",
    ],
  },
  {
    id: "post-sales",
    title: "Resuelve la postventa",
    description: "Aprende a manejar casos después de la compra: novedades, reclamos y seguimiento.",
    outcome: "Podrás priorizar casos y mantener trazabilidad del pedido.",
    page: "post-sales",
    action: "Ir a postventa",
    icon: PackageCheck,
    accent: "rose",
    lessons: [
      "Crea o identifica un caso",
      "Prioriza por urgencia",
      "Actualiza el estado hasta resolverlo",
    ],
  },
];

const MISSIONS = [
  {
    id: "mission-overview",
    title: "Revisa tu Centro de Operaciones",
    description: "Ubica conversaciones, pedidos, automatizaciones e integraciones desde una sola vista.",
    page: "overview",
  },
  {
    id: "mission-conversation",
    title: "Abre una conversación",
    description: "Revisa quién es el cliente, qué ha comprado y quién está atendiendo.",
    page: "conversations",
  },
  {
    id: "mission-copilot",
    title: "Hazle una pregunta al Copiloto",
    description: "Prueba: “¿Qué necesita mi atención hoy?”",
    page: "overview",
  },
  {
    id: "mission-automation",
    title: "Explora una automatización",
    description: "Mira las plantillas y revisa cómo se conectan un trigger y una acción.",
    page: "automations",
  },
  {
    id: "mission-analytics",
    title: "Encuentra tu rentabilidad",
    description: "Ve más allá de las ventas y revisa utilidad, entrega y productos.",
    page: "analytics",
  },
];

function lessonId(moduleId: string, index: number) {
  return `${moduleId}:${index}`;
}

function readProgress() {
  try {
    const raw = localStorage.getItem(PROGRESS_KEY);
    if (!raw) return new Set<string>();
    const parsed = JSON.parse(raw);
    return new Set<string>(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set<string>();
  }
}

export default function LearnDiaglobPage({ onNavigate }: LearnDiaglobPageProps) {
  const [completed, setCompleted] = useState<Set<string>>(() => readProgress());

  useEffect(() => {
    localStorage.setItem(PROGRESS_KEY, JSON.stringify(Array.from(completed)));
  }, [completed]);

  const totalLessons = useMemo(
    () => MODULES.reduce((sum, module) => sum + module.lessons.length, 0),
    [],
  );
  const completedLessons = Array.from(completed).filter((id) => id.includes(":")).length;
  const progress = totalLessons ? Math.round((completedLessons / totalLessons) * 100) : 0;

  const nextModule = MODULES.find((module) =>
    module.lessons.some((_, index) => !completed.has(lessonId(module.id, index))),
  ) || MODULES[0];

  function toggleLesson(id: string) {
    setCompleted((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function markMissionDone(id: string) {
    setCompleted((current) => {
      const next = new Set(current);
      next.add(id);
      return next;
    });
  }

  return (
    <div className="learn-diaglob">
      <section className="learn-hero">
        <div className="learn-hero-copy">
          <div className="learn-eyebrow">
            <Sparkles size={15} />
            <span>APRENDE DIAGLOB</span>
          </div>
          <h1>Aprende haciendo.</h1>
          <p>
            Domina Diaglob con recorridos cortos que te llevan directamente a
            las herramientas reales del producto.
          </p>
          <div className="learn-hero-actions">
            <button
              type="button"
              className="learn-primary-button"
              onClick={() => onNavigate(nextModule.page)}
            >
              Continuar aprendiendo
              <ChevronRight size={17} />
            </button>
            <span>{completedLessons} de {totalLessons} pasos completados</span>
          </div>
        </div>

        <div className="learn-progress-card">
          <div className="learn-progress-ring" style={{ "--learn-progress": `${progress}%` } as React.CSSProperties}>
            <div>
              <strong>{progress}%</strong>
              <span>completado</span>
            </div>
          </div>
          <div className="learn-progress-copy">
            <span>Siguiente recomendado</span>
            <strong>{nextModule.title}</strong>
            <p>{nextModule.outcome}</p>
          </div>
        </div>
      </section>

      <section className="learn-section">
        <div className="learn-section-heading">
          <div>
            <span className="learn-section-kicker">MISIONES</span>
            <h2>Empieza con cinco acciones reales</h2>
            <p>No necesitas estudiar Diaglob antes de usarlo. Haz estas acciones y aprende mientras avanzas.</p>
          </div>
        </div>

        <div className="learn-missions">
          {MISSIONS.map((mission, index) => {
            const done = completed.has(mission.id);
            return (
              <article className={`learn-mission ${done ? "is-done" : ""}`} key={mission.id}>
                <div className="learn-mission-number">
                  {done ? <Check size={16} /> : index + 1}
                </div>
                <div className="learn-mission-copy">
                  <strong>{mission.title}</strong>
                  <p>{mission.description}</p>
                </div>
                <div className="learn-mission-actions">
                  <button
                    type="button"
                    className="learn-text-button"
                    onClick={() => onNavigate(mission.page)}
                  >
                    Ir ahora
                    <ChevronRight size={15} />
                  </button>
                  <button
                    type="button"
                    className="learn-check-button"
                    aria-pressed={done}
                    onClick={() => markMissionDone(mission.id)}
                  >
                    {done ? <CheckCircle2 size={17} /> : <Circle size={17} />}
                    {done ? "Completada" : "Marcar lista"}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="learn-section">
        <div className="learn-section-heading">
          <div>
            <span className="learn-section-kicker">RUTAS CORTAS</span>
            <h2>¿Qué quieres aprender a hacer?</h2>
            <p>Elige por resultado. Cada ruta contiene solo los conceptos necesarios para ejecutar la tarea.</p>
          </div>
        </div>

        <div className="learn-module-grid">
          {MODULES.map((module) => {
            const Icon = module.icon;
            const moduleCompleted = module.lessons.every((_, index) =>
              completed.has(lessonId(module.id, index)),
            );
            const moduleProgress = module.lessons.filter((_, index) =>
              completed.has(lessonId(module.id, index)),
            ).length;

            return (
              <article className="learn-module-card" key={module.id}>
                <header className="learn-module-header">
                  <div className={`learn-module-icon ${module.accent}`}>
                    <Icon size={21} />
                  </div>
                  <div className="learn-module-title">
                    <span>{moduleProgress}/{module.lessons.length} pasos</span>
                    <h3>{module.title}</h3>
                  </div>
                  {moduleCompleted && (
                    <span className="learn-complete-badge">
                      <CheckCircle2 size={14} />
                      Lista
                    </span>
                  )}
                </header>

                <p className="learn-module-description">{module.description}</p>

                <div className="learn-outcome">
                  <span>Resultado</span>
                  <p>{module.outcome}</p>
                </div>

                <div className="learn-lessons">
                  {module.lessons.map((lesson, index) => {
                    const id = lessonId(module.id, index);
                    const done = completed.has(id);
                    return (
                      <button
                        type="button"
                        className={`learn-lesson ${done ? "is-done" : ""}`}
                        key={id}
                        onClick={() => toggleLesson(id)}
                        aria-pressed={done}
                      >
                        {done ? <CheckCircle2 size={17} /> : <Circle size={17} />}
                        <span>{lesson}</span>
                      </button>
                    );
                  })}
                </div>

                <button
                  type="button"
                  className="learn-module-action"
                  onClick={() => onNavigate(module.page)}
                >
                  {module.action}
                  <ChevronRight size={16} />
                </button>
              </article>
            );
          })}
        </div>
      </section>

      <section className="learn-help-card">
        <div className="learn-help-icon">
          <Bot size={24} />
        </div>
        <div>
          <span>APRENDE EN CUALQUIER PANTALLA</span>
          <h2>También puedes preguntarle al Copiloto.</h2>
          <p>
            Abre el Copiloto desde cualquier vista y pregunta “¿Qué puedo hacer
            aquí?” o “Explícame esta pantalla”. Diaglob usa el contexto de la
            página actual para orientarte.
          </p>
        </div>
      </section>
    </div>
  );
}
