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
  updated: "Última actualización: 3 de octubre de 2026",
  intro: "Esta política explica cómo Diaglob trata la información cuando usas nuestra plataforma de conversaciones, comercio, automatización e inteligencia para ecommerce, incluyendo las herramientas opcionales de medición publicitaria.",
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
    { title: "13. Cookies, almacenamiento local y tecnologías necesarias", paragraphs: ["Usamos almacenamiento local, cookies técnicas y señales similares cuando son necesarias para mantener sesiones, seguridad, idioma, tema, preferencias y funcionamiento básico del sitio. También almacenamos tu elección de privacidad para no pedirla en cada visita. Estas funciones necesarias no dependen del consentimiento de medición publicitaria."] },
    { title: "14. Medición publicitaria y consentimiento", paragraphs: ["Meta Pixel y TikTok Pixel son herramientas opcionales. Permanecen desactivadas hasta que autorices la categoría Publicidad y medición desde el aviso de cookies.", "Puedes rechazar esta categoría y seguir usando Diaglob. Puedes cambiar o retirar tu autorización posteriormente desde el control Cookies disponible en la interfaz. Al retirarla, Diaglob deja de iniciar nuevos envíos de eventos publicitarios y elimina de su almacenamiento local los datos de atribución de marketing guardados por Diaglob. Los datos que ya hayan sido procesados por un proveedor antes de la retirada quedan sujetos a sus propias políticas y obligaciones legales."] },
    { title: "15. Meta Pixel", paragraphs: ["Si autorizas Publicidad y medición y configuramos Meta Pixel, podemos compartir con Meta Platforms eventos como visualizaciones de página, inicio o finalización de registro y señales de campaña necesarias para medir atribución y rendimiento publicitario.", "Según la configuración y el funcionamiento de las herramientas de Meta, el proveedor puede recibir información técnica disponible en una solicitud web, datos del dispositivo o navegador, URL o página visitada, hora del evento, identificadores publicitarios o de campaña y cookies asociadas a sus herramientas.", "No enviamos deliberadamente a Meta mediante nuestros eventos de publicidad el contenido de conversaciones, archivos de Google, contraseñas, tokens OAuth, datos completos de pago ni otras categorías sensibles de información empresarial."] },
    { title: "16. TikTok Pixel", paragraphs: ["Si autorizas Publicidad y medición y configuramos TikTok Pixel, podemos compartir con TikTok eventos como visualizaciones, leads y registros completados para medir campañas, atribuir conversiones y optimizar publicidad.", "TikTok indica que su Pixel puede procesar información del anuncio o evento, marca de tiempo, dirección IP, agente de usuario, cookies y determinados metadatos o interacciones del sitio. Sus tecnologías publicitarias pueden incluir identificadores como _ttp, ttcsid, ttcsid_<pixel code> y ttclid, según configuración y disponibilidad.", "No enviamos deliberadamente a TikTok mediante nuestros eventos de publicidad el contenido de conversaciones, archivos de Google, contraseñas, tokens OAuth, datos completos de pago ni otras categorías sensibles de información empresarial."] },
    { title: "17. Atribución de campañas", paragraphs: ["Cuando autorizas Publicidad y medición, Diaglob puede guardar temporalmente en almacenamiento local parámetros de atribución como utm_source, utm_medium, utm_campaign, utm_content, utm_term, fbclid o ttclid para relacionar una campaña con acciones posteriores, por ejemplo un registro. Si no autorizas publicidad o retiras el consentimiento, Diaglob no mantiene esta atribución local para fines publicitarios."] },
    { title: "18. Analítica técnica y registros", paragraphs: ["Podemos recopilar eventos técnicos, registros de errores, métricas de uso y datos del navegador necesarios para operar, proteger, diagnosticar y mejorar el servicio. Estos registros operativos son distintos de la categoría opcional Publicidad y medición. Procuramos limitar los datos a lo necesario para esos fines."] },
    { title: "19. Cómo usamos la información", paragraphs: ["Usamos la información para proporcionar y mantener Diaglob, autenticar usuarios, operar integraciones, procesar contenido solicitado, prevenir abuso, resolver incidencias, medir publicidad cuando existe autorización y cumplir obligaciones aplicables."] },
    { title: "20. Proveedores y subprocesadores", paragraphs: ["Podemos utilizar proveedores de infraestructura, autenticación, pagos, comunicaciones, analítica o inteligencia artificial para operar el servicio. Cuando una función habilitada lo requiere, esto puede incluir Amazon Bedrock para procesar el contenido necesario para esa función. Para medición publicitaria opcional podemos utilizar Meta Platforms y TikTok únicamente cuando dicha categoría esté autorizada y configurada. Los proveedores reciben información según la función correspondiente y sus propios términos."] },
    { title: "21. Seguridad", paragraphs: ["Adoptamos medidas razonables para proteger la información frente a acceso, alteración, pérdida o divulgación no autorizada. Ningún sistema de internet puede garantizar seguridad absoluta."] },
    { title: "22. Retención de datos", paragraphs: ["Conservamos la información durante la vigencia de la cuenta y por el tiempo razonablemente necesario para los fines descritos, resolver disputas, aplicar acuerdos y cumplir obligaciones legales. Los datos de atribución guardados localmente por Diaglob se eliminan cuando retiras el consentimiento publicitario desde nuestro control de cookies."] },
    { title: "23. Tus derechos", paragraphs: ["Según la legislación aplicable, puedes solicitar acceso, corrección, actualización, exportación, restricción o eliminación de cierta información personal. Las organizaciones son responsables de atender solicitudes sobre los datos de sus propios clientes."] },
    { title: "24. Eliminación de cuenta y datos", paragraphs: ["Puedes solicitar eliminación de tu cuenta o datos contactándonos. La eliminación puede estar sujeta a plazos razonables, copias de respaldo temporales y obligaciones legales o de seguridad."] },
    { title: "25. Procesamiento internacional", paragraphs: ["La información puede procesarse en países donde operen Diaglob o sus proveedores, incluidos proveedores de medición publicitaria cuando los autorices. Cuando aplica, buscamos usar salvaguardas razonables para ese procesamiento."] },
    { title: "26. Privacidad de menores", paragraphs: ["Diaglob está dirigido a usuarios empresariales y no está diseñado para menores. No buscamos recopilar deliberadamente información personal de menores."] },
    { title: "27. Cambios a esta política", paragraphs: ["Podemos actualizar esta política para reflejar cambios en el servicio, la ley, las herramientas publicitarias o nuestras prácticas. Publicaremos la versión actualizada con una fecha de última actualización."] },
    { title: "28. Contacto", paragraphs: ["Diaglob es operado por Adrian Felipe Restrepo Guerra desde Bogotá, Colombia. Para preguntas sobre privacidad, solicitudes de datos o esta política, escribe a privacy@diaglob.tech.", "El uso de datos recibidos de las API de Google se ajusta a la Política de Datos de Usuario de los Servicios API de Google, incluidos los requisitos de Uso Limitado aplicables."] },
  ],
};

const privacyEn: LegalDocument = {
  eyebrow: "LEGAL",
  title: "Privacy Policy",
  updated: "Last updated: October 3, 2026",
  intro: "This policy explains how Diaglob handles information when you use our ecommerce conversations, commerce, automation, and intelligence platform, including optional advertising measurement tools.",
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
    { title: "13. Necessary cookies, local storage, and similar technologies", paragraphs: ["We use local storage, technical cookies, and similar signals when needed to maintain sessions, security, language, theme, preferences, and basic website operation. We also store your privacy choice so we do not ask on every visit. These necessary functions do not depend on advertising-measurement consent."] },
    { title: "14. Advertising measurement and consent", paragraphs: ["Meta Pixel and TikTok Pixel are optional tools. They remain disabled until you authorize the Advertising and measurement category through the cookie notice.", "You may reject this category and continue using Diaglob. You may later change or withdraw permission through the Cookies control in the interface. After withdrawal, Diaglob stops initiating new advertising event transmissions and removes marketing-attribution data stored locally by Diaglob. Information already processed by a provider before withdrawal remains subject to that provider's own policies and legal obligations."] },
    { title: "15. Meta Pixel", paragraphs: ["If you authorize Advertising and measurement and we configure Meta Pixel, we may share events with Meta Platforms such as page views, registration starts or completions, and campaign signals needed to measure attribution and advertising performance.", "Depending on configuration and the operation of Meta's business tools, the provider may receive technical information available in a web request, device or browser information, the URL or page visited, event time, advertising or campaign identifiers, and cookies associated with its tools.", "We do not deliberately send Meta through our advertising events the content of conversations, Google files, passwords, OAuth tokens, full payment details, or other sensitive categories of business information."] },
    { title: "16. TikTok Pixel", paragraphs: ["If you authorize Advertising and measurement and we configure TikTok Pixel, we may share events with TikTok such as page views, leads, and completed registrations to measure campaigns, attribute conversions, and optimize advertising.", "TikTok states that its Pixel may process ad or event information, timestamps, IP addresses, user agents, cookies, and certain site metadata or interactions. Its advertising technologies may include identifiers such as _ttp, ttcsid, ttcsid_<pixel code>, and ttclid depending on configuration and availability.", "We do not deliberately send TikTok through our advertising events the content of conversations, Google files, passwords, OAuth tokens, full payment details, or other sensitive categories of business information."] },
    { title: "17. Campaign attribution", paragraphs: ["When you authorize Advertising and measurement, Diaglob may temporarily store campaign-attribution parameters in local storage, such as utm_source, utm_medium, utm_campaign, utm_content, utm_term, fbclid, or ttclid, to associate a campaign with later actions such as registration. If you do not authorize advertising or withdraw consent, Diaglob does not retain this local attribution for advertising purposes."] },
    { title: "18. Technical analytics and logging", paragraphs: ["We may collect technical events, error logs, usage metrics, and browser data needed to operate, secure, diagnose, and improve the service. These operational records are separate from the optional Advertising and measurement category. We aim to limit information to what is needed for those purposes."] },
    { title: "19. How information is used", paragraphs: ["We use information to provide and maintain Diaglob, authenticate users, operate integrations, process requested content, prevent abuse, resolve incidents, measure advertising when authorized, and meet applicable obligations."] },
    { title: "20. Service providers and subprocessors", paragraphs: ["We may use infrastructure, authentication, payment, communications, analytics, or artificial-intelligence providers to operate the service. When an enabled feature requires it, this may include Amazon Bedrock to process content needed for that feature. For optional advertising measurement, we may use Meta Platforms and TikTok only when that category is authorized and configured. Providers receive information according to the relevant function and their own terms."] },
    { title: "21. Security", paragraphs: ["We use reasonable measures to protect information against unauthorized access, alteration, loss, or disclosure. No internet-based system can guarantee absolute security."] },
    { title: "22. Data retention", paragraphs: ["We retain information during the account term and for the reasonably necessary period to meet the purposes described, resolve disputes, enforce agreements, and meet legal obligations. Marketing-attribution data stored locally by Diaglob is removed when you withdraw advertising consent through our cookie control."] },
    { title: "23. Your rights", paragraphs: ["Depending on applicable law, you may request access, correction, update, export, restriction, or deletion of certain personal information. Organizations are responsible for requests concerning their own customer data."] },
    { title: "24. Account and data deletion", paragraphs: ["You may request deletion of your account or data by contacting us. Deletion may be subject to reasonable processing periods, temporary backups, and legal or security obligations."] },
    { title: "25. International processing", paragraphs: ["Information may be processed in countries where Diaglob or its providers operate, including advertising-measurement providers when you authorize them. Where applicable, we seek to use reasonable safeguards for that processing."] },
    { title: "26. Children's privacy", paragraphs: ["Diaglob is intended for business users and is not designed for children. We do not knowingly seek to collect personal information from children."] },
    { title: "27. Changes to this policy", paragraphs: ["We may update this policy to reflect changes in the service, law, advertising tools, or our practices. We will publish the updated version with a last-updated date."] },
    { title: "28. Contact", paragraphs: ["Diaglob is operated by Adrian Felipe Restrepo Guerra from Bogotá, Colombia. For privacy questions, data requests, or questions about this policy, contact privacy@diaglob.tech.", "Our use of information received from Google APIs adheres to the Google API Services User Data Policy, including applicable Limited Use requirements."] },
  ],
};

const privacyPtBr: LegalDocument = {
  eyebrow: "LEGAL",
  title: "Política de Privacidade",
  updated: "Última atualização: 3 de outubro de 2026",
  intro: "Esta política explica como o Diaglob trata informações quando você usa nossa plataforma de conversas, comércio, automação e inteligência para ecommerce, incluindo ferramentas opcionais de medição publicitária.",
  sections: [
    { title: "1. Introdução", paragraphs: ["O Diaglob respeita a privacidade das pessoas e empresas que utilizam o serviço. Esta política se aplica ao site, ao aplicativo e às integrações habilitadas pelos usuários."] },
    { title: "2. Informações que coletamos", paragraphs: ["Coletamos as informações necessárias para criar contas, operar workspaces, fornecer funcionalidades solicitadas, manter a segurança e atender solicitações de suporte."] },
    { title: "3. Informações de conta e perfil", paragraphs: ["Podem incluir nome, endereço de e-mail, credenciais de acesso administradas por nossos provedores de autenticação, organização, preferências de idioma e configurações da conta."] },
    { title: "4. Dados de clientes e negócios", paragraphs: ["As organizações podem carregar ou gerar dados de clientes, conversas, pedidos, produtos, agentes, automações e fontes de conhecimento. Tratamos esses dados para prestar o serviço à organização que os controla."] },
    { title: "5. Dados de ecommerce e integrações", paragraphs: ["Quando você conecta uma loja ou provedor, o Diaglob pode processar os dados que você autorizar, como produtos, pedidos, estoque, clientes ou configurações, apenas para as funcionalidades habilitadas no seu workspace."] },
    { title: "6. Dados de integrações do Google", paragraphs: ["Quando você conecta Google Drive, Google Docs ou Google Sheets, o Diaglob pode acessar somente os arquivos, documentos, planilhas, metadados e permissões autorizados por OAuth e necessários para a funcionalidade solicitada."] },
    { title: "7. Como usamos dados de usuários do Google", paragraphs: ["Usamos dados do Google para exibir recursos autorizados, importar conteúdo selecionado, sincronizar alterações solicitadas e criar fontes de conhecimento no Diaglob. Não usamos esses dados para finalidades não relacionadas à funcionalidade solicitada."] },
    { title: "8. Proteção dos dados do Google", paragraphs: ["Limitamos o acesso aos dados e credenciais do Google aos processos necessários para fornecer as funcionalidades autorizadas. Aplicamos controles técnicos e operacionais razoáveis de acordo com a natureza do serviço."] },
    { title: "9. Compartilhamento de dados do Google", paragraphs: ["Não vendemos dados de usuários do Google nem os usamos para publicidade. Não compartilhamos dados do Google com terceiros, salvo quando necessário para prestar o serviço solicitado, cumprir obrigação legal ou seguir sua instrução."] },
    { title: "10. Retenção e exclusão de dados do Google", paragraphs: ["Mantemos dados importados do Google e metadados de conexão enquanto forem necessários para a fonte de conhecimento ou conta correspondente. Você pode desconectar o Google, excluir fontes ou solicitar a exclusão de dados conforme esta política."] },
    { title: "11. Tratamento de tokens OAuth", paragraphs: ["Tokens OAuth são usados exclusivamente para manter integrações autorizadas. Eles são protegidos por mecanismos de armazenamento destinados a limitar sua exposição e não são exibidos na interface nem incluídos intencionalmente nos registros da aplicação."] },
    { title: "12. Outras integrações", paragraphs: ["O Diaglob pode integrar-se a serviços como Shopify, WooCommerce ou outros provedores disponíveis. Cada integração está sujeita às permissões concedidas, às configurações da organização e aos termos do respectivo terceiro."] },
    { title: "13. Cookies, armazenamento local e tecnologias necessárias", paragraphs: ["Usamos armazenamento local, cookies técnicos e sinais semelhantes quando necessários para manter sessões, segurança, idioma, tema, preferências e o funcionamento básico do site. Também armazenamos sua escolha de privacidade para não solicitá-la a cada visita. Essas funções necessárias não dependem do consentimento para medição publicitária."] },
    { title: "14. Medição publicitária e consentimento", paragraphs: ["Meta Pixel e TikTok Pixel são ferramentas opcionais. Elas permanecem desativadas até que você autorize a categoria Publicidade e medição no aviso de cookies.", "Você pode rejeitar essa categoria e continuar usando o Diaglob. Também pode alterar ou retirar sua autorização posteriormente pelo controle Cookies disponível na interface. Após a retirada, o Diaglob deixa de iniciar novos envios de eventos publicitários e remove do armazenamento local os dados de atribuição de marketing salvos pelo Diaglob. Informações já processadas por um provedor antes da retirada permanecem sujeitas às políticas e obrigações legais desse provedor."] },
    { title: "15. Meta Pixel", paragraphs: ["Se você autorizar Publicidade e medição e configurarmos o Meta Pixel, poderemos compartilhar com a Meta Platforms eventos como visualizações de página, início ou conclusão de cadastro e sinais de campanha necessários para medir atribuição e desempenho publicitário.", "Dependendo da configuração e do funcionamento das ferramentas empresariais da Meta, o provedor pode receber informações técnicas disponíveis em uma solicitação web, dados do dispositivo ou navegador, URL ou página visitada, horário do evento, identificadores publicitários ou de campanha e cookies associados às suas ferramentas.", "Não enviamos deliberadamente à Meta, por meio de nossos eventos publicitários, o conteúdo de conversas, arquivos do Google, senhas, tokens OAuth, dados completos de pagamento nem outras categorias sensíveis de informações empresariais."] },
    { title: "16. TikTok Pixel", paragraphs: ["Se você autorizar Publicidade e medição e configurarmos o TikTok Pixel, poderemos compartilhar com o TikTok eventos como visualizações, leads e cadastros concluídos para medir campanhas, atribuir conversões e otimizar publicidade.", "O TikTok informa que seu Pixel pode processar informações do anúncio ou evento, registros de data e hora, endereço IP, user agent, cookies e determinados metadados ou interações do site. Suas tecnologias publicitárias podem incluir identificadores como _ttp, ttcsid, ttcsid_<pixel code> e ttclid, conforme a configuração e a disponibilidade.", "Não enviamos deliberadamente ao TikTok, por meio de nossos eventos publicitários, o conteúdo de conversas, arquivos do Google, senhas, tokens OAuth, dados completos de pagamento nem outras categorias sensíveis de informações empresariais."] },
    { title: "17. Atribuição de campanhas", paragraphs: ["Quando você autoriza Publicidade e medição, o Diaglob pode armazenar temporariamente no armazenamento local parâmetros de atribuição como utm_source, utm_medium, utm_campaign, utm_content, utm_term, fbclid ou ttclid para relacionar uma campanha a ações posteriores, por exemplo um cadastro. Se você não autorizar publicidade ou retirar o consentimento, o Diaglob não mantém essa atribuição local para fins publicitários."] },
    { title: "18. Analítica técnica e registros", paragraphs: ["Podemos coletar eventos técnicos, registros de erros, métricas de uso e dados do navegador necessários para operar, proteger, diagnosticar e melhorar o serviço. Esses registros operacionais são distintos da categoria opcional Publicidade e medição. Procuramos limitar os dados ao necessário para essas finalidades."] },
    { title: "19. Como usamos as informações", paragraphs: ["Usamos as informações para fornecer e manter o Diaglob, autenticar usuários, operar integrações, processar conteúdo solicitado, prevenir abuso, resolver incidentes, medir publicidade quando houver autorização e cumprir obrigações aplicáveis."] },
    { title: "20. Provedores e subprocessadores", paragraphs: ["Podemos utilizar provedores de infraestrutura, autenticação, pagamentos, comunicações, analítica ou inteligência artificial para operar o serviço. Quando uma funcionalidade habilitada exigir, isso pode incluir o Amazon Bedrock para processar o conteúdo necessário àquela funcionalidade. Para medição publicitária opcional, podemos utilizar Meta Platforms e TikTok somente quando essa categoria estiver autorizada e configurada. Os provedores recebem informações de acordo com a função correspondente e seus próprios termos."] },
    { title: "21. Segurança", paragraphs: ["Adotamos medidas razoáveis para proteger as informações contra acesso, alteração, perda ou divulgação não autorizados. Nenhum sistema baseado na internet pode garantir segurança absoluta."] },
    { title: "22. Retenção de dados", paragraphs: ["Mantemos as informações durante a vigência da conta e pelo período razoavelmente necessário para as finalidades descritas, resolver disputas, fazer cumprir acordos e atender obrigações legais. Os dados de atribuição armazenados localmente pelo Diaglob são removidos quando você retira o consentimento publicitário pelo nosso controle de cookies."] },
    { title: "23. Seus direitos", paragraphs: ["De acordo com a legislação aplicável, você pode solicitar acesso, correção, atualização, exportação, restrição ou exclusão de determinadas informações pessoais. As organizações são responsáveis por atender solicitações relacionadas aos dados de seus próprios clientes."] },
    { title: "24. Exclusão de conta e dados", paragraphs: ["Você pode solicitar a exclusão de sua conta ou de seus dados entrando em contato conosco. A exclusão pode estar sujeita a prazos razoáveis de processamento, backups temporários e obrigações legais ou de segurança."] },
    { title: "25. Processamento internacional", paragraphs: ["As informações podem ser processadas em países onde o Diaglob ou seus provedores operam, incluindo provedores de medição publicitária quando você os autorizar. Quando aplicável, buscamos utilizar salvaguardas razoáveis para esse processamento."] },
    { title: "26. Privacidade de menores", paragraphs: ["O Diaglob é destinado a usuários empresariais e não foi projetado para menores de idade. Não buscamos coletar intencionalmente informações pessoais de menores."] },
    { title: "27. Alterações desta política", paragraphs: ["Podemos atualizar esta política para refletir mudanças no serviço, na legislação, nas ferramentas publicitárias ou em nossas práticas. Publicaremos a versão atualizada com a data da última atualização."] },
    { title: "28. Contato", paragraphs: ["O Diaglob é operado por Adrian Felipe Restrepo Guerra a partir de Bogotá, Colômbia. Para dúvidas sobre privacidade, solicitações relacionadas a dados ou esta política, escreva para privacy@diaglob.tech.", "Nosso uso das informações recebidas das APIs do Google segue a Política de Dados de Usuário dos Serviços de API do Google, incluindo os requisitos aplicáveis de Uso Limitado."] },
  ],
};

const termsEs: LegalDocument = {
  eyebrow: "LEGAL",
  title: "Términos de servicio",
  updated: "Última actualización: 3 de octubre de 2026",
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
    { title: "27. Contacto", paragraphs: ["Diaglob es operado por Adrian Felipe Restrepo Guerra desde Bogotá, Colombia. Para preguntas sobre estos términos o asuntos legales, escribe a legal@diaglob.tech. Para facturación, escribe a billing@diaglob.tech."] },
  ],
};

const termsEn: LegalDocument = {
  eyebrow: "LEGAL",
  title: "Terms of Service",
  updated: "Last updated: October 3, 2026",
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
    { title: "27. Contact", paragraphs: ["Diaglob is operated by Adrian Felipe Restrepo Guerra from Bogotá, Colombia. For questions about these terms or legal matters, contact legal@diaglob.tech. For billing, contact billing@diaglob.tech."] },
  ],
};

const termsPtBr: LegalDocument = {
  eyebrow: "LEGAL",
  title: "Termos de Serviço",
  updated: "Última atualização: 3 de outubro de 2026",
  intro: "Estes termos regulam o uso do Diaglob, marca operada por Adrian Felipe Restrepo Guerra, pessoa física com operação principal em Bogotá, Colômbia. Ao criar uma conta, acessar ou usar o serviço, você aceita estes termos em seu próprio nome ou em nome da organização que representa.",
  sections: [
    { title: "1. Aceitação dos termos", paragraphs: ["Ao usar o Diaglob, você aceita estes termos e as políticas incorporadas por referência. Se não concordar, não utilize o serviço."] },
    { title: "2. Descrição do Diaglob", paragraphs: ["O Diaglob oferece ferramentas para conversas, comércio, automação, analítica, inteligência de clientes, agentes e conhecimento para operações de ecommerce."] },
    { title: "3. Elegibilidade e contas", paragraphs: ["Você deve ter capacidade para aceitar estes termos e fornecer informações de conta verdadeiras. Você é responsável por proteger suas credenciais de acesso."] },
    { title: "4. Responsabilidades da conta", paragraphs: ["Você é responsável pelas atividades realizadas em sua conta, pelas pessoas às quais concede acesso e por comunicar acessos não autorizados de forma oportuna."] },
    { title: "5. Organizações e workspaces", paragraphs: ["Quem cria ou administra uma organização controla seus membros, lojas, configurações e dados empresariais. Você deve ter autorização para administrar os dados que incluir."] },
    { title: "6. Lojas e serviços conectados", paragraphs: ["Você pode conectar lojas e serviços de terceiros somente quando tiver autorização. O Diaglob opera de acordo com as permissões concedidas e não controla a disponibilidade nem as políticas desses terceiros."] },
    { title: "7. Integrações do Google", paragraphs: ["As integrações do Google são habilitadas por OAuth e acessam apenas os recursos autorizados para a funcionalidade solicitada. Você deve respeitar os termos do Google e administrar suas conexões pelo Diaglob."] },
    { title: "8. Outras integrações", paragraphs: ["Integrações com Shopify, WooCommerce ou outros provedores estão sujeitas aos próprios termos, permissões, limites e alterações de serviço desses terceiros."] },
    { title: "9. Conteúdo e dados de clientes", paragraphs: ["Você mantém os direitos sobre seu conteúdo e seus dados. Você concede ao Diaglob as permissões limitadas necessárias para hospedar, processar e exibir esse conteúdo com a finalidade de prestar o serviço."] },
    { title: "10. Uso aceitável", paragraphs: ["Você deve usar o Diaglob de forma lícita, respeitosa e coerente com estes termos, a documentação disponível e os direitos de terceiros."] },
    { title: "11. Atividades proibidas", paragraphs: ["Você não pode usar o serviço para violar a lei, infringir direitos, distribuir conteúdo malicioso, interferir no serviço, contornar controles, acessar sistemas sem autorização ou enviar comunicações não permitidas."] },
    { title: "12. Propriedade intelectual", paragraphs: ["O Diaglob e seus elementos protegidos pertencem aos respectivos titulares. Estes termos não concedem direitos sobre marcas, software ou conteúdo do Diaglob além do uso permitido do serviço."] },
    { title: "13. Serviços de terceiros", paragraphs: ["Serviços de terceiros podem mudar, ser suspensos ou impor condições próprias. O Diaglob não é responsável por decisões, falhas ou conteúdo desses serviços."] },
    { title: "14. Planos de assinatura", paragraphs: ["Funcionalidades, limites e preços dependem do plano selecionado e das informações apresentadas ao contratar ou administrar a assinatura."] },
    { title: "15. Faturamento", paragraphs: ["Você concorda em pagar as cobranças aplicáveis ao seu plano pelo provedor de pagamentos disponível. Quando a Paddle processar o pagamento como Merchant of Record, a cobrança, os impostos, os comprovantes e determinadas obrigações de pagamento serão administrados de acordo com os termos da Paddle e a legislação aplicável."] },
    { title: "16. Alterações de plano", paragraphs: ["Alterações de plano, período de cobrança e seus efeitos no preço seguem as opções apresentadas no aplicativo e as regras do provedor de pagamentos quando aplicável."] },
    { title: "17. Cancelamento", paragraphs: ["Você pode cancelar conforme as opções disponíveis em sua conta. Salvo indicação em contrário ou exigência legal, você manterá o acesso até o fim do período já pago e a assinatura não será renovada depois dessa data. O cancelamento não elimina obrigações de pagamento acumuladas antes de produzir efeito. Consulte também nossa Política de Reembolso."] },
    { title: "18. Disponibilidade do serviço", paragraphs: ["Buscamos manter o Diaglob disponível, mas o serviço pode ser afetado por manutenção, mudanças, provedores externos, internet ou eventos fora do nosso controle."] },
    { title: "19. Funcionalidades beta ou experimentais", paragraphs: ["Algumas funcionalidades podem ser identificadas como beta, preliminares ou experimentais. Elas podem mudar, ser limitadas ou retiradas e são fornecidas para avaliação sem garantias adicionais."] },
    { title: "20. Funcionalidades geradas por IA", paragraphs: ["Respostas, recomendações ou automações geradas por IA podem ser incompletas ou imprecisas. Você deve revisá-las antes de utilizá-las em decisões comerciais, comunicações ou ações operacionais."] },
    { title: "21. Isenções de garantia", paragraphs: ["Na medida permitida pela legislação, o Diaglob é fornecido no estado em que se encontra e conforme disponibilidade. Não garantimos que atenderá a todos os requisitos, funcionará sem interrupções ou estará livre de erros."] },
    { title: "22. Limitação de responsabilidade", paragraphs: ["Na medida permitida pela legislação aplicável, o Diaglob não será responsável por danos indiretos, incidentais, especiais ou consequenciais, nem por perda de dados, receitas ou lucros decorrentes do uso ou da impossibilidade de uso do serviço."] },
    { title: "23. Suspensão ou encerramento", paragraphs: ["Podemos suspender ou encerrar o acesso quando isso for razoavelmente necessário para proteger o serviço, cumprir a legislação, responder a riscos de segurança, tratar falta de pagamento ou violações materiais."] },
    { title: "24. Dados após o encerramento", paragraphs: ["Após o encerramento, o acesso pode terminar e os dados podem ser excluídos de acordo com nossos períodos de retenção, backups e obrigações legais. Recomendamos exportar as informações necessárias antes de cancelar."] },
    { title: "25. Alterações dos termos", paragraphs: ["Podemos atualizar estes termos. A versão atualizada será publicada nesta página, e o uso continuado após sua entrada em vigor poderá constituir aceitação quando permitido pela legislação."] },
    { title: "26. Lei aplicável", paragraphs: ["Estes termos são regidos pelas leis da República da Colômbia, sem limitar normas obrigatórias e direitos de proteção ao consumidor que possam ser aplicáveis na jurisdição do cliente."] },
    { title: "27. Contato", paragraphs: ["O Diaglob é operado por Adrian Felipe Restrepo Guerra a partir de Bogotá, Colômbia. Para dúvidas sobre estes termos ou assuntos jurídicos, escreva para legal@diaglob.tech. Para faturamento, escreva para billing@diaglob.tech."] },
  ],
};

const documents = {
  privacy: { es: privacyEs, en: privacyEn, "pt-BR": privacyPtBr },
  terms: { es: termsEs, en: termsEn, "pt-BR": termsPtBr },
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
  const language: "es" | "en" | "pt-BR" = rawLanguage;
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
    const metadata = {
      es: {
        privacyTitle: "Política de privacidad | Diaglob",
        termsTitle: "Términos de servicio | Diaglob",
        privacyDescription: "Conoce cómo Diaglob trata la información, las integraciones y la medición publicitaria opcional.",
        termsDescription: "Consulta los términos que regulan el uso de Diaglob.",
      },
      en: {
        privacyTitle: "Privacy Policy | Diaglob",
        termsTitle: "Terms of Service | Diaglob",
        privacyDescription: "Learn how Diaglob handles information, integrations, and optional advertising measurement.",
        termsDescription: "Read the terms governing use of Diaglob.",
      },
      "pt-BR": {
        privacyTitle: "Política de Privacidade | Diaglob",
        termsTitle: "Termos de Serviço | Diaglob",
        privacyDescription: "Saiba como o Diaglob trata informações, integrações e a medição publicitária opcional.",
        termsDescription: "Consulte os termos que regulam o uso do Diaglob.",
      },
    }[language];

    setMetadata(
      isPrivacy ? metadata.privacyTitle : metadata.termsTitle,
      isPrivacy ? metadata.privacyDescription : metadata.termsDescription,
      isPrivacy ? "/privacy" : "/terms",
    );
  }, [kind, language]);

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
