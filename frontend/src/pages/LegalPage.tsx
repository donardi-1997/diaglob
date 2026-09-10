import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Moon, Sparkles, Sun } from "lucide-react";

type LegalPageKind = "privacy" | "terms";

type LegalSection = {
  title: string;
  paragraphs: string[];
  bullets?: string[];
};

type LegalDocument = {
  eyebrow: string;
  title: string;
  updated: string;
  intro: string;
  sections: LegalSection[];
};

const privacyEs: LegalDocument = {
  eyebrow: "LEGAL",
  title: "Política de privacidad",
  updated: "Última actualización: 1 de septiembre de 2026",
  intro: "Esta política explica cómo Diaglob trata la información cuando usas nuestra plataforma de conversaciones, comercio, automatización e inteligencia para ecommerce.",
  sections: [
    { title: "1. Introducción", paragraphs: ["Diaglob respeta la privacidad de las personas y empresas que usan el servicio. Esta política aplica al sitio web, la aplicación y las integraciones habilitadas por los usuarios."] },
    { title: "2. Información que recopilamos", paragraphs: ["Recopilamos información necesaria para crear cuentas, operar espacios de trabajo, proporcionar funciones solicitadas, mantener la seguridad y atender solicitudes de soporte."] },
    { title: "3. Información de cuenta y perfil", paragraphs: ["Puede incluir nombre, correo electrónico, credenciales de acceso administradas por nuestros proveedores de autenticación, organización, preferencias de idioma y configuraciones de la cuenta."] },
    { title: "4. Datos de clientes y negocios", paragraphs: ["Las organizaciones pueden cargar o generar datos de clientes, conversaciones, pedidos, productos, agentes, automatizaciones y fuentes de conocimiento. Tratamos estos datos para prestar el servicio a la organización que los controla."] },
    { title: "5. Datos de ecommerce e integraciones", paragraphs: ["Cuando conectas una tienda o proveedor, Diaglob puede procesar los datos que autorices, como productos, pedidos, inventario, clientes o configuraciones, únicamente para las funciones activadas en tu espacio de trabajo."] },
    { title: "6. Datos de integraciones de Google", paragraphs: ["Cuando conectas Google Drive, Google Docs o Google Sheets, Diaglob puede acceder únicamente a los archivos, documentos, hojas, metadatos y permisos que autorices mediante OAuth y que sean necesarios para la función solicitada."] },
    { title: "7. Uso de datos de usuarios de Google", paragraphs: ["Usamos los datos de Google para mostrar recursos autorizados, importar contenido seleccionado, sincronizar cambios solicitados y crear fuentes de conocimiento dentro de Diaglob. No usamos estos datos para fines no relacionados con la funcionalidad solicitada."] },
    { title: "8. Protección de datos de Google", paragraphs: ["Limitamos el acceso a los datos y credenciales de Google a los procesos necesarios para prestar las funciones autorizadas. Aplicamos controles técnicos y operativos razonables acordes con la naturaleza del servicio."] },
    { title: "9. Compartición de datos de Google", paragraphs: ["No vendemos datos de usuarios de Google ni los usamos para publicidad. No compartimos datos de Google con terceros salvo cuando sea necesario para prestar el servicio solicitado, cumplir una obligación legal o con tu instrucción."] },
    { title: "10. Retención y eliminación de datos de Google", paragraphs: ["Conservamos los datos de Google importados y los metadatos de conexión mientras sean necesarios para la fuente de conocimiento o cuenta correspondiente. Puedes desconectar Google, eliminar fuentes o solicitar eliminación de datos conforme a esta política."] },
    { title: "11. Manejo de tokens OAuth", paragraphs: ["Los tokens OAuth se usan exclusivamente para mantener las integraciones autorizadas. Se protegen mediante mecanismos de almacenamiento diseñados para limitar su exposición y no se muestran en la interfaz ni se incluyen deliberadamente en registros de aplicación."] },
    { title: "12. Otras integraciones", paragraphs: ["Diaglob puede integrarse con servicios como Shopify, WooCommerce u otros proveedores disponibles. Cada integración está sujeta a los permisos otorgados, la configuración de la organización y los términos del tercero correspondiente."] },
    { title: "13. Cookies e información técnica", paragraphs: ["Podemos usar almacenamiento local, cookies técnicas y señales similares para mantener sesiones, preferencias, seguridad, idioma, tema y funcionamiento básico del sitio."] },
    { title: "14. Analítica y registros", paragraphs: ["Podemos recopilar eventos técnicos, registros de errores, métricas de uso y datos del navegador para operar, proteger y mejorar el servicio. Procuramos limitar estos datos a lo necesario para esos fines."] },
    { title: "15. Cómo usamos la información", paragraphs: ["Usamos la información para proporcionar y mantener Diaglob, autenticar usuarios, operar integraciones, procesar contenido solicitado, prevenir abuso, resolver incidencias y cumplir obligaciones aplicables."] },
    { title: "16. Proveedores y subprocesadores", paragraphs: ["Podemos utilizar proveedores de infraestructura, autenticación, pagos, comunicaciones, analítica o inteligencia artificial para operar el servicio. Cuando una función habilitada lo requiere, esto puede incluir Amazon Bedrock para procesar el contenido necesario para esa función. Estos proveedores solo reciben información necesaria para sus funciones."] },
    { title: "17. Seguridad", paragraphs: ["Adoptamos medidas razonables para proteger la información frente a acceso, alteración, pérdida o divulgación no autorizada. Ningún sistema de internet puede garantizar seguridad absoluta."] },
    { title: "18. Retención de datos", paragraphs: ["Conservamos la información durante la vigencia de la cuenta y por el tiempo razonablemente necesario para los fines descritos, resolver disputas, aplicar acuerdos y cumplir obligaciones legales."] },
    { title: "19. Tus derechos", paragraphs: ["Según la legislación aplicable, puedes solicitar acceso, corrección, actualización, exportación, restricción o eliminación de cierta información personal. Las organizaciones son responsables de atender solicitudes sobre los datos de sus propios clientes."] },
    { title: "20. Eliminación de cuenta y datos", paragraphs: ["Puedes solicitar eliminación de tu cuenta o datos contactándonos. La eliminación puede estar sujeta a plazos razonables, copias de respaldo temporales y obligaciones legales o de seguridad."] },
    { title: "21. Procesamiento internacional", paragraphs: ["La información puede procesarse en países donde operen Diaglob o sus proveedores. Cuando aplica, buscamos usar salvaguardas razonables para ese procesamiento."] },
    { title: "22. Privacidad de menores", paragraphs: ["Diaglob está dirigido a usuarios empresariales y no está diseñado para menores. No buscamos recopilar deliberadamente información personal de menores."] },
    { title: "23. Cambios a esta política", paragraphs: ["Podemos actualizar esta política para reflejar cambios en el servicio, la ley o nuestras prácticas. Publicaremos la versión actualizada con una fecha de última actualización."] },
    { title: "24. Contacto", paragraphs: ["Diaglob es operado por Adrian Felipe Restrepo Guerra desde Bogotá, Colombia. Para preguntas sobre privacidad, solicitudes de datos o esta política, escribe a adrianguerra9703@gmail.com.", "El uso de datos recibidos de las API de Google se ajusta a la Política de Datos de Usuario de los Servicios API de Google, incluidos los requisitos de Uso Limitado aplicables."] },
  ],
};

const privacyEn: LegalDocument = {
  eyebrow: "LEGAL",
  title: "Privacy Policy",
  updated: "Last updated: September 1, 2026",
  intro: "This policy explains how Diaglob handles information when you use our ecommerce conversations, commerce, automation, and intelligence platform.",
  sections: [
    { title: "1. Introduction", paragraphs: ["Diaglob respects the privacy of people and businesses using the service. This policy applies to our website, application, and integrations enabled by users."] },
    { title: "2. Information we collect", paragraphs: ["We collect information needed to create accounts, operate workspaces, provide requested features, maintain security, and respond to support requests."] },
    { title: "3. Account and profile information", paragraphs: ["This may include your name, email address, authentication credentials managed by our identity providers, organization, language preferences, and account settings."] },
    { title: "4. Customer and business data", paragraphs: ["Organizations may upload or generate customer, conversation, order, product, agent, automation, and knowledge-source data. We process this data to provide the service to the organization that controls it."] },
    { title: "5. Ecommerce and integration data", paragraphs: ["When you connect a store or provider, Diaglob may process the data you authorize, such as products, orders, inventory, customers, or settings, only for features enabled in your workspace."] },
    { title: "6. Google integration data", paragraphs: ["When you connect Google Drive, Google Docs, or Google Sheets, Diaglob may access only the files, documents, spreadsheets, metadata, and permissions authorized through OAuth and needed for the requested feature."] },
    { title: "7. How we use Google user data", paragraphs: ["We use Google data to show authorized resources, import selected content, synchronize requested changes, and create knowledge sources in Diaglob. We do not use it for purposes unrelated to requested functionality."] },
    { title: "8. Protecting Google user data", paragraphs: ["We limit access to Google data and credentials to the processes needed to provide authorized features. We use reasonable technical and operational controls appropriate to the service."] },
    { title: "9. Google data sharing", paragraphs: ["We do not sell Google user data or use it for advertising. We do not share Google data with third parties except as needed to provide the requested service, comply with law, or follow your instruction."] },
    { title: "10. Google data retention and deletion", paragraphs: ["We retain imported Google data and connection metadata while needed for the relevant knowledge source or account. You may disconnect Google, delete sources, or request data deletion under this policy."] },
    { title: "11. OAuth token handling", paragraphs: ["OAuth tokens are used only to maintain authorized integrations. They are protected through storage controls designed to limit exposure and are not shown in the interface or intentionally included in application logs."] },
    { title: "12. Other integrations", paragraphs: ["Diaglob may integrate with services such as Shopify, WooCommerce, or other available providers. Each integration is subject to granted permissions, organization settings, and the relevant third-party terms."] },
    { title: "13. Cookies and technical information", paragraphs: ["We may use local storage, technical cookies, and similar signals to maintain sessions, preferences, security, language, theme, and basic website operation."] },
    { title: "14. Analytics and logging", paragraphs: ["We may collect technical events, error logs, usage metrics, and browser data to operate, secure, and improve the service. We aim to limit this information to what is needed for those purposes."] },
    { title: "15. How information is used", paragraphs: ["We use information to provide and maintain Diaglob, authenticate users, operate integrations, process requested content, prevent abuse, resolve incidents, and meet applicable obligations."] },
    { title: "16. Service providers and subprocessors", paragraphs: ["We may use infrastructure, authentication, payment, communications, analytics, or artificial-intelligence providers to operate the service. When an enabled feature requires it, this may include Amazon Bedrock to process content needed for that feature. Providers receive only information needed for their functions."] },
    { title: "17. Security", paragraphs: ["We use reasonable measures to protect information against unauthorized access, alteration, loss, or disclosure. No internet-based system can guarantee absolute security."] },
    { title: "18. Data retention", paragraphs: ["We retain information during the account term and for the reasonably necessary period to meet the purposes described, resolve disputes, enforce agreements, and meet legal obligations."] },
    { title: "19. Your rights", paragraphs: ["Depending on applicable law, you may request access, correction, update, export, restriction, or deletion of certain personal information. Organizations are responsible for requests concerning their own customer data."] },
    { title: "20. Account and data deletion", paragraphs: ["You may request deletion of your account or data by contacting us. Deletion may be subject to reasonable processing periods, temporary backups, and legal or security obligations."] },
    { title: "21. International processing", paragraphs: ["Information may be processed in countries where Diaglob or its providers operate. Where applicable, we seek to use reasonable safeguards for that processing."] },
    { title: "22. Children's privacy", paragraphs: ["Diaglob is intended for business users and is not designed for children. We do not knowingly seek to collect personal information from children."] },
    { title: "23. Changes to this policy", paragraphs: ["We may update this policy to reflect changes in the service, law, or our practices. We will publish the updated version with a last-updated date."] },
    { title: "24. Contact", paragraphs: ["Diaglob is operated by Adrian Felipe Restrepo Guerra from Bogotá, Colombia. For privacy questions, data requests, or questions about this policy, contact adrianguerra9703@gmail.com.", "Our use of information received from Google APIs adheres to the Google API Services User Data Policy, including applicable Limited Use requirements."] },
  ],
};

const termsEs: LegalDocument = {
  eyebrow: "LEGAL",
  title: "Términos de servicio",
  updated: "Última actualización: 10 de septiembre de 2026",
  intro: "Estos términos regulan el uso de Diaglob, marca operada por Adrian Felipe Restrepo Guerra, persona natural con operación principal en Bogotá, Colombia. Al crear una cuenta, acceder o usar el servicio, aceptas estos términos en nombre propio o de la organización que representas.",
  sections: [
    { title: "1. Aceptación de los términos", paragraphs: ["Al usar Diaglob aceptas estos términos y las políticas incorporadas por referencia. Si no estás de acuerdo, no uses el servicio."] },
    { title: "2. Descripción de Diaglob", paragraphs: ["Diaglob ofrece herramientas para conversaciones, comercio, automatización, analítica, inteligencia de clientes, agentes y conocimiento para operaciones de ecommerce."] },
    { title: "3. Elegibilidad y cuentas", paragraphs: ["Debes tener capacidad para aceptar estos términos y proporcionar información de cuenta veraz. Eres responsable de mantener tus credenciales protegidas."] },
    { title: "4. Responsabilidades de cuenta", paragraphs: ["Eres responsable de la actividad realizada desde tu cuenta, de las personas a las que otorgas acceso y de informar accesos no autorizados de forma oportuna."] },
    { title: "5. Organizaciones y espacios de trabajo", paragraphs: ["Quien crea o administra una organización controla sus miembros, tiendas, configuraciones y datos empresariales. Debes contar con autorización para administrar los datos que incorporas."] },
    { title: "6. Tiendas y servicios conectados", paragraphs: ["Puedes conectar tiendas y servicios de terceros solo cuando tengas autorización. Diaglob opera según los permisos concedidos y no controla la disponibilidad ni las políticas de esos terceros."] },
    { title: "7. Integraciones de Google", paragraphs: ["Las integraciones de Google se habilitan mediante OAuth y solo acceden a los recursos autorizados para la función solicitada. Debes respetar los términos de Google y administrar tus conexiones desde Diaglob."] },
    { title: "8. Otras integraciones", paragraphs: ["Las integraciones con Shopify, WooCommerce u otros proveedores están sujetas a sus propios términos, permisos, límites y cambios de servicio."] },
    { title: "9. Contenido y datos de clientes", paragraphs: ["Conservas los derechos sobre tu contenido y datos. Otorgas a Diaglob los permisos limitados necesarios para alojar, procesar y mostrar ese contenido con el fin de prestar el servicio."] },
    { title: "10. Uso aceptable", paragraphs: ["Debes usar Diaglob de forma lícita, respetuosa y coherente con estos términos, la documentación disponible y los derechos de terceros."] },
    { title: "11. Actividades prohibidas", paragraphs: ["No puedes usar el servicio para vulnerar la ley, infringir derechos, distribuir contenido malicioso, interferir con el servicio, evadir controles, acceder sin autorización o enviar comunicaciones no permitidas."] },
    { title: "12. Propiedad intelectual", paragraphs: ["Diaglob y sus elementos protegidos pertenecen a sus respectivos titulares. Estos términos no otorgan derechos sobre marcas, software o contenido de Diaglob fuera del uso permitido del servicio."] },
    { title: "13. Servicios de terceros", paragraphs: ["Los servicios de terceros pueden cambiar, suspenderse o imponer condiciones propias. Diaglob no es responsable por decisiones, fallas o contenido de dichos servicios."] },
    { title: "14. Planes de suscripción", paragraphs: ["Las funciones, límites y precios dependen del plan seleccionado y de la información mostrada al contratar o administrar la suscripción."] },
    { title: "15. Facturación", paragraphs: ["Aceptas pagar los cargos aplicables a tu plan mediante el proveedor de pagos disponible. Cuando Paddle procese el pago como Merchant of Record, el cobro, los impuestos, comprobantes y determinadas obligaciones de pago se gestionarán conforme a sus términos y a la normativa aplicable."] },
    { title: "16. Cambios de plan", paragraphs: ["Los cambios de plan, períodos y sus efectos de precio se rigen por las opciones mostradas en la aplicación y por las reglas del proveedor de pagos cuando corresponda."] },
    { title: "17. Cancelación", paragraphs: ["Puedes cancelar conforme a las opciones disponibles en tu cuenta. Salvo que se indique lo contrario o la ley exija otra cosa, conservarás acceso hasta el final del período ya pagado y la suscripción no se renovará después de esa fecha. La cancelación no elimina obligaciones de pago acumuladas antes de su efecto. Consulta también nuestra Política de reembolsos."] },
    { title: "18. Disponibilidad del servicio", paragraphs: ["Buscamos mantener Diaglob disponible, pero el servicio puede verse afectado por mantenimiento, cambios, proveedores externos, internet o eventos fuera de nuestro control."] },
    { title: "19. Funciones beta o experimentales", paragraphs: ["Algunas funciones pueden identificarse como beta, preliminares o experimentales. Pueden cambiar, limitarse o retirarse y se proporcionan para evaluación sin garantías adicionales."] },
    { title: "20. Funcionalidad generada por IA", paragraphs: ["Las respuestas, recomendaciones o automatizaciones generadas por IA pueden ser incompletas o inexactas. Debes revisarlas antes de utilizarlas en decisiones comerciales, comunicaciones o acciones operativas."] },
    { title: "21. Descargos", paragraphs: ["En la medida permitida por la ley, Diaglob se proporciona tal como está y según disponibilidad. No garantizamos que satisfaga todos los requisitos, sea ininterrumpido o esté libre de errores."] },
    { title: "22. Limitación de responsabilidad", paragraphs: ["En la medida permitida por la ley aplicable, Diaglob no será responsable por daños indirectos, incidentales, especiales, consecuentes, pérdida de datos, ingresos o beneficios derivados del uso o imposibilidad de uso del servicio."] },
    { title: "23. Suspensión o terminación", paragraphs: ["Podemos suspender o terminar acceso cuando sea razonablemente necesario para proteger el servicio, cumplir la ley, responder a riesgos de seguridad, falta de pago o incumplimientos materiales."] },
    { title: "24. Datos después de la terminación", paragraphs: ["Tras la terminación, el acceso puede finalizar y los datos pueden eliminarse conforme a nuestros plazos de retención, respaldos y obligaciones legales. Recomendamos exportar lo que necesites antes de cancelar."] },
    { title: "25. Cambios a los términos", paragraphs: ["Podemos actualizar estos términos. La versión actualizada se publicará en esta página y el uso continuado después de su vigencia puede constituir aceptación cuando la ley lo permita."] },
    { title: "26. Ley aplicable", paragraphs: ["Estos términos se rigen por las leyes de la República de Colombia, sin perjuicio de las normas imperativas y derechos de protección al consumidor que resulten aplicables en la jurisdicción del cliente."] },
    { title: "27. Contacto", paragraphs: ["Diaglob es operado por Adrian Felipe Restrepo Guerra desde Bogotá, Colombia. Para preguntas sobre estos términos, facturación o asuntos legales, escribe a adrianguerra9703@gmail.com."] },
  ],
};

const termsEn: LegalDocument = {
  eyebrow: "LEGAL",
  title: "Terms of Service",
  updated: "Last updated: September 10, 2026",
  intro: "These terms govern the use of Diaglob, a brand operated by Adrian Felipe Restrepo Guerra, an individual based in Bogotá, Colombia. By creating an account, accessing, or using the service, you accept them for yourself or the organization you represent.",
  sections: [
    { title: "1. Acceptance of terms", paragraphs: ["By using Diaglob, you accept these terms and policies incorporated by reference. Do not use the service if you do not agree."] },
    { title: "2. Description of Diaglob", paragraphs: ["Diaglob provides tools for ecommerce conversations, commerce, automation, analytics, customer intelligence, agents, and knowledge operations."] },
    { title: "3. Eligibility and accounts", paragraphs: ["You must be able to accept these terms and provide accurate account information. You are responsible for protecting your account credentials."] },
    { title: "4. Account responsibilities", paragraphs: ["You are responsible for activity under your account, people you authorize, and promptly reporting unauthorized access."] },
    { title: "5. Organizations and workspaces", paragraphs: ["The person who creates or administers an organization controls its members, stores, settings, and business data. You must have authority to administer the data you add."] },
    { title: "6. Connected stores and third-party services", paragraphs: ["You may connect stores and third-party services only when authorized. Diaglob operates under granted permissions and does not control their availability or policies."] },
    { title: "7. Google integrations", paragraphs: ["Google integrations use OAuth and access only resources authorized for the requested feature. You must comply with Google terms and manage connections through Diaglob."] },
    { title: "8. Other integrations", paragraphs: ["Integrations with Shopify, WooCommerce, and other providers are subject to their own terms, permissions, limits, and service changes."] },
    { title: "9. Customer content and data", paragraphs: ["You retain rights in your content and data. You grant Diaglob the limited permissions needed to host, process, and display it to provide the service."] },
    { title: "10. Acceptable use", paragraphs: ["You must use Diaglob lawfully, respectfully, and consistently with these terms, available documentation, and third-party rights."] },
    { title: "11. Prohibited activities", paragraphs: ["You may not use the service to break the law, infringe rights, distribute malicious content, interfere with the service, bypass controls, gain unauthorized access, or send prohibited communications."] },
    { title: "12. Intellectual property", paragraphs: ["Diaglob and its protected elements belong to their respective owners. These terms do not grant rights in Diaglob trademarks, software, or content beyond permitted service use."] },
    { title: "13. Third-party services", paragraphs: ["Third-party services may change, be suspended, or impose their own terms. Diaglob is not responsible for their decisions, failures, or content."] },
    { title: "14. Subscription plans", paragraphs: ["Features, limits, and prices depend on the selected plan and information shown when subscribing or managing your subscription."] },
    { title: "15. Billing", paragraphs: ["You agree to pay applicable plan charges through the available payment provider. When Paddle processes a payment as Merchant of Record, payment collection, taxes, receipts, and certain payment obligations are handled under Paddle terms and applicable law."] },
    { title: "16. Plan changes", paragraphs: ["Plan and billing-period changes, including pricing effects, follow the options shown in the application and applicable payment-provider rules."] },
    { title: "17. Cancellation", paragraphs: ["You may cancel through account options. Unless otherwise stated or required by law, access continues until the end of the already-paid billing period and the subscription will not renew afterward. Cancellation does not remove payment obligations accrued before it takes effect. See our Refund Policy as well."] },
    { title: "18. Service availability", paragraphs: ["We seek to keep Diaglob available, but service may be affected by maintenance, changes, external providers, the internet, or events outside our control."] },
    { title: "19. Beta or experimental features", paragraphs: ["Some features may be identified as beta, preview, or experimental. They may change, be limited, or be withdrawn and are provided for evaluation without additional warranties."] },
    { title: "20. AI-generated functionality", paragraphs: ["AI-generated responses, recommendations, or automations may be incomplete or inaccurate. Review them before using them for commercial decisions, communications, or operational actions."] },
    { title: "21. Disclaimers", paragraphs: ["To the extent permitted by law, Diaglob is provided as is and as available. We do not guarantee that it will meet every requirement, be uninterrupted, or be error-free."] },
    { title: "22. Limitation of liability", paragraphs: ["To the extent permitted by applicable law, Diaglob is not liable for indirect, incidental, special, consequential, data, revenue, or profit losses arising from use of or inability to use the service."] },
    { title: "23. Suspension or termination", paragraphs: ["We may suspend or terminate access when reasonably necessary to protect the service, comply with law, respond to security risks, address non-payment, or address material breaches."] },
    { title: "24. Data after termination", paragraphs: ["After termination, access may end and data may be deleted under retention periods, backups, and legal obligations. Export information you need before cancellation."] },
    { title: "25. Changes to terms", paragraphs: ["We may update these terms. The updated version will be posted here, and continued use after its effective date may constitute acceptance where law permits."] },
    { title: "26. Governing law", paragraphs: ["These terms are governed by the laws of the Republic of Colombia, without limiting any mandatory consumer-protection rights that may apply in the customer jurisdiction."] },
    { title: "27. Contact", paragraphs: ["Diaglob is operated by Adrian Felipe Restrepo Guerra from Bogotá, Colombia. For questions about these terms, billing, or legal matters, contact adrianguerra9703@gmail.com."] },
  ],
};

const documents = {
  privacy: { es: privacyEs, en: privacyEn },
  terms: { es: termsEs, en: termsEn },
};

function setMetadata(title: string, description: string, path: string) {
  document.title = title;

  const setMeta = (selector: string, content: string) => {
    let element = document.head.querySelector<HTMLMetaElement>(selector);
    if (!element) {
      element = document.createElement("meta");
      element.setAttribute("name", "description");
      document.head.appendChild(element);
    }
    element.content = content;
  };

  setMeta('meta[name="description"]', description);

  let canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!canonical) {
    canonical = document.createElement("link");
    canonical.rel = "canonical";
    document.head.appendChild(canonical);
  }
  canonical.href = `https://diaglob.tech${path}`;
}

export default function LegalPage({ kind }: { kind: LegalPageKind }) {
  const { i18n } = useTranslation();
  const rawLanguage = i18n.language.startsWith("en") ? "en" : i18n.language.startsWith("pt") ? "pt-BR" : "es";
  // Legal documents fall back to English for pt-BR
  const language: "es" | "en" = rawLanguage === "pt-BR" ? "en" : rawLanguage as "es" | "en";
  const documentContent = documents[kind][language];
  const [theme, setTheme] = useState(
    localStorage.getItem("diaglob-theme") || "dark",
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("diaglob-theme", theme);
  }, [theme]);

  useEffect(() => {
    const isPrivacy = kind === "privacy";
    setMetadata(
      isPrivacy ? "Privacy Policy | Diaglob" : "Terms of Service | Diaglob",
      isPrivacy
        ? "Learn how Diaglob handles information and Google integrations."
        : "Read the terms governing use of Diaglob.",
      isPrivacy ? "/privacy" : "/terms",
    );
  }, [kind]);

  const changeLanguage = (nextLanguage: "es" | "en" | "pt-BR") => {
    i18n.changeLanguage(nextLanguage);
    localStorage.setItem("diaglob-language", nextLanguage);
  };

  return (
    <div className="landing-page legal-page">
      <header className="landing-navbar">
        <div className="landing-container">
          <div className="landing-navbar-inner">
            <Link className="landing-brand" to="/" aria-label="Diaglob home">
              <div className="brand-mark"><Sparkles size={20} /></div>
              <div>
                <div className="brand-name">DIAGLOB</div>
                <div className="brand-version">AI COMMERCE</div>
              </div>
            </Link>
            <div className="landing-controls">
              <div className="landing-lang-switch" aria-label="Language">
                <button className={rawLanguage === "es" ? "active" : ""} onClick={() => changeLanguage("es")}>ES</button>
                <button className={rawLanguage === "en" ? "active" : ""} onClick={() => changeLanguage("en")}>EN</button>
                <button className={rawLanguage === "pt-BR" ? "active" : ""} onClick={() => changeLanguage("pt-BR")}>PT-BR</button>
              </div>
              <button className="theme-toggle" onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")} aria-label="Toggle theme">
                {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="legal-main">
        <article className="legal-document">
          <div className="legal-intro">
            <span className="landing-hero-eyebrow">{documentContent.eyebrow}</span>
            <h1>{documentContent.title}</h1>
            <p className="legal-updated">{documentContent.updated}</p>
            <p className="legal-lede">{documentContent.intro}</p>
          </div>
          <div className="legal-sections">
            {documentContent.sections.map((section: LegalSection) => (
              <section key={section.title} className="legal-section">
                <h2>{section.title}</h2>
                {section.paragraphs.map((paragraph: string) => <p key={paragraph}>{paragraph}</p>)}
                {section.bullets && <ul>{section.bullets.map((bullet: string) => <li key={bullet}>{bullet}</li>)}</ul>}
              </section>
            ))}
          </div>
        </article>
      </main>
    </div>
  );
}
