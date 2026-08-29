import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  es: {
    translation: {
      brandTagline: "Conversaciones inteligentes para comercio global",

      overview: "Resumen",
    plans: "Planes",

      plansTitle: "Planes",
      plansBillingEyebrow:
        "FACTURACIÓN",
      plansChoosePayment:
        "Elige cómo quieres pagar",
      plansPaymentHelp:
        "Paga por un período más largo y obtén un mejor precio.",

      plansSubtitle:
        "Elige la capacidad y el período de facturación que mejor se adapten a tu operación.",

      plansRecommended: "Recomendado",
      plansCurrentPlan: "Plan actual",
      plansChoosePlan: "Elegir plan",
      plansUpgrade: "Mejorar plan",
      plansDowngrade: "Cambiar al renovar",

      plansMonthlyPrice: "Precio mensual",
      plansPeriodPrice: "Precio del período",
      plansCurrentPeriod: "Período actual",

      plansImmediateUpgrade: "Upgrade disponible ahora",
      plansCalculating: "Calculando...",
      plansCheckingProration:
        "Consultando la prorrata con Paddle",
      plansPayDifferenceToday:
        "Solo pagas la diferencia proporcional hoy.",
      plansNextRenewalFullPrice:
        "En tu próxima renovación, el cobro será por el valor completo del nuevo plan según tu período de facturación.",
      plansPriceUnavailable:
        "Precio no disponible",
      plansProrationUnavailable:
        "No pudimos calcular la prorrata. Intenta nuevamente.",

      plansChangeAtRenewal:
        "Cambio al renovar",
      plansNoProrationDowngrade:
        "Mantienes tu plan actual hasta finalizar el período pagado. No se aplica prorrata.",
      plansNewPeriodAtRenewal:
        "Nuevo período al renovar",
      plansDurationAtRenewal:
        "El cambio de duración comenzará en tu próxima renovación. No se aplica prorrata.",
      plansScheduledUpgrade:
        "Cambio disponible al renovar",
      plansScheduledUpgradeHelp:
        "El plan y el nuevo período podrán aplicarse cuando termine tu período actual. No se aplica prorrata.",

      plansActiveStore: "tienda activa",
      plansActiveStores: "tiendas activas",

      plansScheduledChange: "Cambio programado",
      plansScheduledChangeTitle: "Cambio de plan programado",
      plansCanceling: "Cancelando...",
      plansCancelChange: "Cancelar cambio",
      plansNoActivePlan: "Sin plan activo",
      plansNoActivePlanHelp:
        "Elige un plan para activar las funciones de DIAGLOB.",
      plansChangePeriodAtRenewal:
        "Cambiar período al renovar",
      plansAvailableAtRenewal:
        "Disponible al renovar",
      plansOpeningPayment: "Abriendo pago...",
      plansConfirmUpgrade: "Confirmar upgrade",
      plansCurrentPlanLabel: "Plan actual",
      plansNewPlanLabel: "Nuevo plan",
      plansPayToday: "Pagarás hoy",
      plansProrationExplanation:
        "Paddle calcula automáticamente el tiempo no utilizado de tu plan actual.",
      plansNewPlanProratedCharge:
        "Cargo proporcional nuevo plan",
      plansCurrentPlanCredit:
        "Crédito plan actual",
      plansNextRenewal:
        "Próxima renovación",
      plansCurrentPeriodLockedPrefix:
        "Tu suscripción mantiene su período actual de",
      plansCurrentPeriodLockedHelp:
        "El período de facturación queda fijo mientras la suscripción esté activa. Al cambiar de plan, conservarás el mismo período contratado.",
      plansDaysRemaining:
        "Quedan {{count}} días",
      plansOneDayRemaining:
        "Queda 1 día",
      plansRenewsToday:
        "Renueva hoy",
      plansNextRenewalDate:
        "Próxima renovación: {{date}}",
      plansNextMonthlyPrice:
        "Próximo precio mensual",
      plansPerMonthEquivalent:
        "al mes",
      plansScheduling: "Programando...",
      plansScheduleForRenewal:
        "Programar para renovación",

      plansRenewalEyebrow:
        "RENOVACIÓN",
      plansAutoRenewTitle:
        "Renovación automática",
      plansAutoRenewEnabled:
        "Renovación automática activada",
      plansAutoRenewHelp:
        "Mantén tu plan activo sin interrupciones. DIAGLOB renovará automáticamente tu suscripción al finalizar cada período.",
      plansAutoRenewEnabledHelp:
        "Tu plan se renovará automáticamente al finalizar el período.",
      plansAutoRenewDisabled:
        "Renovación automática desactivada",
      plansAutoRenewDisabledHelp:
        "Tu plan permanecerá activo hasta que termine el período pagado. Después, tus tiendas serán suspendidas sin eliminar sus datos.",

      mobileOpenMenu:
        "Abrir menú",
      mobileCloseMenu:
        "Cerrar menú",
      mobileNavigation:
        "Navegación principal",
      logout:
        "Cerrar sesión",
      lightMode:
        "Modo claro",
      darkMode:
        "Modo oscuro",

      plansAutoRenewUpdateError:
        "No fue posible actualizar la renovación automática.",
      plansPlanChangeError:
        "No fue posible procesar el cambio de plan.",
      plansScheduledChangeCanceled:
        "El cambio de plan programado fue cancelado.",
      plansScheduledChangeCancelError:
        "No fue posible cancelar el cambio programado.",
      plansScheduledChangeSuccess:
        "Cambio programado correctamente. Seguirás usando tu plan actual hasta la renovación.",
      plansCancelScheduledChange:
        "Cancelar cambio",

      plansPeriodChangeError:
        "Tu plan actual se factura cada {{currentPeriod}}. El cambio a {{selectedPeriod}} no puede hacerse con prorrata. Debes esperar a que termine el período actual para aplicar el nuevo plan y período.",
      plansChangeToConnector:
        "a",
      plansChangeDate:
        "Fecha del cambio",
      plansProcessing:
        "Procesando...",
      plansPlanChange:
        "Cambio de plan",
      plansScheduleChangeTitle:
        "Programar cambio al renovar",
      plansAdditionalChargeToday:
        "Cobro adicional hoy",
      plansKeepCurrentUntilRenewal:
        "Mantendrás tu plan actual hasta la renovación.",
      commonCancel:
        "Cancelar",

      planRequiredDefault:
        "Necesitas un plan activo para realizar esta acción.",
      noActiveStore:
        "Sin tienda activa",
      selectStore:
        "Seleccionar tienda",

      conversationsLoadError:
        "No fue posible cargar las conversaciones.",
      conversationLoadError:
        "No fue posible cargar la conversación.",
      conversationModeError:
        "No fue posible cambiar el modo de atención.",
      conversationSendError:
        "No fue posible enviar el mensaje.",

      plansMissingCheckoutUrl:
        "No se recibió la URL de pago.",
      plansPaddleNotReady:
        "Paddle todavía no está listo.",
      plansUpgradeError:
        "No fue posible completar el upgrade.",
      plansDowngradeScheduleError:
        "No fue posible programar el cambio de plan.",
      plansBillingPeriodLockedTitle:
        "La duración se mantiene mientras la suscripción esté activa.",
      commonLoading:
        "Cargando...",
      storeSingular:
        "tienda",
      storePlural:
        "tiendas",
      storeActive:
        "Activa",
      storeSuspended:
        "Suspendida",
      plansSelectActiveStores:
        "Selecciona las tiendas que estarán activas",
      plansSelectUpToStores:
        "Puedes seleccionar hasta {{count}} {{stores}}",
      plansStoreActiveSince:
        "Activa desde {{date}}",
      plansDowngradeStoreSelectionHelp:
        "La selección se aplicará únicamente en la renovación. Puedes elegir tiendas activas o suspendidas. Las tiendas suspendidas seleccionadas se activarán cuando entre en vigencia el nuevo plan. Si una tienda seleccionada fue eliminada, DIAGLOB podrá reemplazarla por una tienda que ya esté activa, priorizando la de mayor antigüedad.",
      plansNewStoreLimitHelp:
        "El nuevo límite de tiendas se aplicará únicamente cuando entre en vigencia el nuevo plan.",
      plansNoStoresSuspendedToday:
        "Programar este cambio no suspende ninguna tienda hoy.",
      plansSuspendedStoresRenewalHelp:
        "Las tiendas suspendidas que selecciones se activarán únicamente cuando entre en vigencia el nuevo plan. Si una selección fue eliminada antes de renovar, DIAGLOB usará como respaldo una tienda que ya esté activa.",

      loginI18nConfirmCodeHelp:
        "Escribe el código que Cognito envió a tu correo.",

      agentsI18nEmptyHelp:
        "Crea el primer agente IA para esta organización.",

      loginI18nLoginError:
        "No fue posible iniciar sesión.",
      loginI18nNameRequired:
        "Escribe tu nombre.",
      loginI18nOrganizationRequired:
        "Escribe el nombre de tu empresa.",
      loginI18nCreateError:
        "No fue posible crear la cuenta.",
      loginI18nConfirmError:
        "No fue posible confirmar la cuenta.",
      loginI18nCodeResent:
        "Enviamos un nuevo código a tu correo.",
      loginI18nResendError:
        "No fue posible reenviar el código.",
      loginI18nSubtitle:
        "Inicia sesión para administrar tus conversaciones y tiendas.",
      loginI18nEmail:
        "Correo electrónico",
      loginI18nPassword:
        "Contraseña",
      loginI18nCreateNewAccount:
        "Crear cuenta nueva",
      loginI18nCreateAccount:
        "Crear cuenta",
      loginI18nName:
        "Nombre",
      loginI18nPasswordHint:
        "Usa una contraseña fuerte que cumpla la política configurada en Cognito.",
      loginI18nConfirmEmailTitle:
        "Confirma tu correo",
      loginI18nSigningIn:
        "Ingresando...",
      loginI18nSignIn:
        "Iniciar sesión",
      loginI18nCreating:
        "Creando...",
      loginI18nConfirming:
        "Confirmando...",
      loginI18nConfirmAndEnter:
        "Confirmar y entrar",
      loginI18nOrganizationPlaceholder:
        "Ej. Moda Express",

      agentsI18nLoadError:
        "No fue posible cargar la configuración de agentes.",
      agentsI18nNameRequired:
        "El agente necesita un nombre.",
      agentsI18nRoleRequired:
        "El agente necesita un rol.",
      agentsI18nSaveError:
        "No fue posible guardar el agente.",
      agentsI18nStatusError:
        "No fue posible cambiar el estado del agente.",
      agentsI18nSubtitle:
        "Administra los agentes que atienden tus tiendas y sus fuentes de conocimiento.",
      agentsI18nActive:
        "Activo",
      agentsI18nInactive:
        "Inactivo",
      agentsI18nStores:
        "Tiendas",
      agentsI18nNoStores:
        "Sin tiendas",
      agentsI18nEdit:
        "Editar",
      agentsI18nEditAgent:
        "Editar agente",
      agentsI18nNewAgent:
        "Nuevo agente",
      agentsI18nName:
        "Nombre",
      agentsI18nOrganization:
        "Organización",
      agentsI18nSelectedStores:
        "Tiendas seleccionadas",
      agentsI18nAgentActive:
        "Agente activo",
      agentsI18nCancel:
        "Cancelar",
      agentsI18nDeactivate:
        "Desactivar",
      agentsI18nActivate:
        "Activar",
      agentsI18nSaveChanges:
        "Guardar cambios",
      agentsI18nCreateAgent:
        "Crear agente",
      agentsI18nNamePlaceholder:
        "Ej. Ventas Colombia",
      agentsI18nRolePlaceholder:
        "sales, support...",

      knowledgeI18nLoadError:
        "No fue posible cargar las Knowledge Bases.",
      knowledgeI18nNameRequired:
        "La Knowledge Base necesita un nombre.",
      knowledgeI18nStoreRequired:
        "Selecciona al menos una tienda.",
      knowledgeI18nSaveError:
        "No fue posible guardar la Knowledge Base.",
      knowledgeI18nStatusError:
        "No fue posible cambiar el estado.",
      knowledgeI18nDocumentsLoadError:
        "No fue posible cargar los documentos.",
      knowledgeI18nDocumentUploadError:
        "No fue posible subir el documento.",
      knowledgeI18nDocumentDeleteError:
        "No fue posible eliminar el documento.",

      knowledgeI18nNewKnowledgeBase:
        "Nueva Knowledge Base",
      knowledgeI18nEditKnowledgeBase:
        "Editar Knowledge Base",
      knowledgeI18nWholeOrganization:
        "Toda la organización",
      knowledgeI18nSelectedStores:
        "Tiendas seleccionadas",
      knowledgeI18nActive:
        "Activa",
      knowledgeI18nInactive:
        "Inactiva",
      knowledgeI18nStores:
        "Tiendas",
      knowledgeI18nAllStores:
        "Todas las tiendas",
      knowledgeI18nPendingBedrock:
        "Pendiente de conectar a Bedrock",
      knowledgeI18nDeactivate:
        "Desactivar",
      knowledgeI18nActivate:
        "Activar",
      knowledgeI18nName:
        "Nombre",
      knowledgeI18nNamePlaceholder:
        "Ej. Políticas de devolución",
      knowledgeI18nBedrockPlaceholder:
        "Se asignará al conectar Bedrock",
      knowledgeI18nKnowledgeBaseActive:
        "Knowledge Base activa",
      knowledgeI18nCancel:
        "Cancelar",
      knowledgeI18nSaveChanges:
        "Guardar cambios",
      knowledgeI18nCreateKnowledgeBase:
        "Crear Knowledge Base",
      knowledgeI18nDeleteDocument:
        "Eliminar documento",

      storesI18nLoadError:
        "No fue posible cargar las tiendas y mercados.",
      storesI18nDeletedSuccess:
        "La tienda \"{{name}}\" fue eliminada.",
      storesI18nDeleteError:
        "No fue posible eliminar la tienda.",
      storesI18nNameRequired:
        "Escribe el nombre de la tienda.",
      storesI18nCountryRequired:
        "Selecciona un país o mercado.",
      storesI18nUpdatedSuccess:
        "Tienda actualizada correctamente.",
      storesI18nCreatedSuccess:
        "Tienda creada correctamente.",
      storesI18nPlanLimitReached:
        "Has alcanzado el límite de tiendas activas de tu plan.",
      storesI18nSaveError:
        "No fue posible guardar la tienda.",

      storesI18nLoading:
        "Cargando tiendas y mercados...",
      storesI18nTitle:
        "Tiendas y mercados",
      storesI18nNewStore:
        "Nueva tienda",
      storesI18nActiveStores:
        "Tiendas activas",
      storesI18nAvailableMarkets:
        "Mercados disponibles",
      storesI18nNoStores:
        "Aún no tienes tiendas",
      storesI18nCreateFirstStore:
        "Crear primera tienda",
      storesI18nEmptyHelp:
        "Crea tu primera tienda y selecciona el mercado donde operará.",
      storesI18nDelete:
        "Eliminar",

      storesI18nSlotAvailable:
        "{{count}} cupo disponible",
      storesI18nSlotsAvailable:
        "{{count}} cupos disponibles",

      storesI18nActive:
        "Activa",
      storesI18nSuspended:
        "Suspendida",
      storesI18nNotConnected:
        "Sin conectar",

      storesI18nPlanLimitEyebrow:
        "LÍMITE DEL PLAN",
      storesI18nPlanLimitHelp:
        "Puedes suspender una tienda activa para liberar un cupo y activar otra sin perder productos, clientes, pedidos ni historial.",
      storesI18nViewPlans:
        "Ver planes",

      storesI18nConfirmDeleteEyebrow:
        "CONFIRMAR ELIMINACIÓN",
      storesI18nDeleteStoreTitle:
        "¿Eliminar tienda?",
      storesI18nAboutToDelete:
        "Estás a punto de eliminar",
      storesI18nDeleteWarning:
        "La tienda dejará de estar activa y no aparecerá en las operaciones normales de DIAGLOB.",
      storesI18nDeleting:
        "Eliminando...",
      storesI18nConfirmDelete:
        "Sí, eliminar tienda",

      storesI18nConfigureStore:
        "Configurar tienda",
      storesI18nCountryMarket:
        "País / mercado",
      storesI18nSelectCountry:
        "Selecciona un país",
      storesI18nMarketLockedHelp:
        "El mercado no se cambia después de crear la tienda.",
      storesI18nStoreName:
        "Nombre de la tienda",
      storesI18nNamePlaceholder:
        "Ej. Diaglob Perú",
      storesI18nStoreActive:
        "Tienda activa",
      storesI18nOperational:
        "La tienda está operativa.",
      storesI18nSuspendedHelp:
        "La tienda quedará suspendida. No se eliminarán sus datos, clientes, pedidos ni historial.",
      storesI18nMarket:
        "Mercado",
      storesI18nSaving:
        "Guardando...",
      storesI18nSaveChanges:
        "Guardar cambios",
      storesI18nCreateStore:
        "Crear tienda",

      knowledgeI18nDeleteConfirm:
        "¿Eliminar {{name}}?",
      knowledgeI18nEdit:
        "Editar",

      storesI18nStores:
        "Tiendas",
      storesI18nCancel:
        "Cancelar",

      integrationsTitle:
        "Integraciones",
      integrationsLoading:
        "Cargando integraciones...",
      integrationsConnected:
        "Conectado",
      integrationsDisconnected:
        "Desconectado",
      integrationsConnect:
        "Conectar",
      integrationsDisconnect:
        "Desconectar",
      integrationsCopyWebhook:
        "Copiar webhook",
      integrationsCopyVerifyToken:
        "Copiar verify token",
      integrationsShopifyNoDomain:
        "Sin dominio Shopify",
      integrationsShopifyConnectError:
        "No se pudo iniciar la conexión con Shopify.",
      integrationsShopifyDisconnected:
        "Shopify se desconectó.",
      integrationsShopifyTest:
        "Probar conexión",
      integrationsShopifyTestOk:
        "Conexión verificada correctamente.",
      integrationsShopifyTestError:
        "No se pudo verificar la conexión con Shopify.",
      integrationsShopifySync:
        "Sincronizar productos",
      integrationsShopifySyncOk:
        "Productos sincronizados correctamente.",
      integrationsShopifySyncError:
        "No se pudieron sincronizar los productos.",
      integrationsShopifyOrderCreate:
        "Crear orden",
      integrationsShopifyOrderCreateOk:
        "Orden creada correctamente.",
      integrationsShopifyOrderCreateError:
        "No se pudo crear la orden.",
      integrationsShopifyOrderNoVariants:
        "Sincroniza productos primero para crear órdenes.",
      integrationsShopifyOrderOpenInvoice:
        "Abrir enlace de pago",
      integrationsShopifyOrdersTitle:
        "Órdenes",
      integrationsShopifyOrderEmpty:
        "No hay órdenes aún.",
      integrationsDisconnectError:
        "No se pudo desconectar.",
      integrationsDropiTokenRequired:
        "Ingresa el token de Dropi para conectar.",
      integrationsDropiConnected:
        "Dropi conectado.",
      integrationsDropiDisconnected:
        "Dropi se desconectó.",
      integrationsDropiConnectError:
        "No se pudo conectar Dropi.",
      integrationsDropiTokenPlaceholder:
        "Token de Dropi",
      integrationsCopyError:
        "No se pudo copiar el webhook.",

      integrationsWhatsAppConnected:
        "WhatsApp conectado.",
      integrationsWhatsAppDisconnected:
        "WhatsApp se desconectó.",
      integrationsWhatsAppConnectError:
        "No se pudo conectar WhatsApp.",
      integrationsWhatsAppFieldsRequired:
        "phone_number_id, business_account_id y access_token son obligatorios.",
      integrationsWhatsAppPhonePlaceholder:
        "Phone Number ID",
      integrationsWhatsAppBizPlaceholder:
        "Business Account ID",
      integrationsWhatsAppTokenPlaceholder:
        "Access Token de WhatsApp",

      appI18nViewPlans:
        "Ver planes",
      appI18nChangeTheme:
        "Cambiar tema",

      plansI18nScheduledBannerTitle:
        "Cambio de plan programado",
      plansI18nYourPlanWillChangeFrom:
        "Tu plan cambiará de",
      plansI18nKeepCurrentFeaturesUntilThen:
        "Hasta entonces conservarás todas las funciones de tu plan actual.",
      plansI18nScheduledBadge:
        "Cambio programado",
      plansI18nChangeAtRenewal:
        "Cambio al renovar",
      plansI18nDowngradeRenewalHelp:
        "Mantienes tu plan actual hasta finalizar el período pagado. No se aplica prorrata.",
      plansI18nNewPeriodAtRenewal:
        "Nuevo período al renovar",
      plansI18nPeriodChangeRenewalHelp:
        "El cambio de duración comenzará en tu próxima renovación. No se aplica prorrata.",
      plansI18nAvailableAtRenewalTitle:
        "Cambio disponible al renovar",
      plansI18nPlanAndPeriodRenewalHelp:
        "El plan y el nuevo período podrán aplicarse cuando termine tu período actual. No se aplica prorrata.",
      plansI18nCancel:
        "Cancelar",

      teamI18nUnexpectedError:
        "Ocurrió un error inesperado.",

      loginI18nVerificationSent:
        "Enviamos un código de verificación a {{email}}.",
      loginI18nProvisionError:
        "No fue posible crear tu espacio de trabajo.",

      billingI18nUnitMonth:
        "mes",
      billingI18nUnitMonths:
        "{{count}} meses",
      billingI18nUnitYear:
        "año",

      appI18nPlanRequiredEyebrow:
        "PLAN REQUERIDO",
      appI18nPlanRequiredTitle:
        "No tienes un plan activo",

      billing1Month: "1 mes",
      billing3Months: "3 meses",
      billing6Months: "6 meses",
      billing12Months: "12 meses",

      billingPerMonth: "mes",
      billingPerYear: "año",

      billingSave5: "Ahorra 5%",
      billingSave10: "Ahorra 10%",
      billingSave2Months: "Ahorra 2 meses",

      starterDescription:
        "Para comenzar a vender con automatización.",
      starterFeature1:
        "1 tienda activa",
      starterFeature2:
        "Hasta 1.000 clientes/mes",
      starterFeature3:
        "2 miembros del equipo",
      starterFeature4:
        "WhatsApp multiagente",
      starterFeature5:
        "Automatizaciones básicas",
      starterFeature6:
        "Integración con Shopify",

      growthDescription:
        "Para negocios que empiezan a escalar.",
      growthFeature1:
        "2 tiendas activas",
      growthFeature2:
        "Hasta 5.000 clientes/mes",
      growthFeature3:
        "5 miembros del equipo",
      growthFeature4:
        "IA para ventas",
      growthFeature5:
        "Recuperación de carritos",
      growthFeature6:
        "Segmentación de clientes",

      proDescription:
        "Para operaciones multitienda y multipaís.",
      proFeature1:
        "3 tiendas activas",
      proFeature2:
        "Hasta 10.000 clientes/mes",
      proFeature3:
        "10 miembros del equipo",
      proFeature4:
        "Agentes IA avanzados",
      proFeature5:
        "Analítica avanzada",
      proFeature6:
        "Automatizaciones avanzadas",

      scaleDescription:
        "Para operaciones de alto volumen.",
      scaleFeature1:
        "5 tiendas activas",
      scaleFeature2:
        "Hasta 25.000 clientes/mes",
      scaleFeature3:
        "15 miembros del equipo",
      scaleFeature4:
        "Operación multipaís",
      scaleFeature5:
        "Prioridad de soporte",
      scaleFeature6:
        "Funciones avanzadas de comercio",
      conversations: "Conversaciones",
      customers: "Clientes",
      team: "Equipo",
      agents: "Agentes IA",
      knowledge: "Conocimiento",
      commerce: "Comercio",
      automations: "Automatizaciones",
      analytics: "Analítica",
      settings: "Configuración",

      dashboardTitle: "Centro de operaciones",
      dashboardSubtitle:
        "Gestiona conversaciones, agentes y conocimiento desde un solo lugar.",

      activeConversations: "Conversaciones activas",
      aiResolved: "Resueltas por IA",
      conversionRate: "Conversión",
      revenueInfluenced: "Ventas asistidas",

      liveActivity: "Actividad reciente",
      liveActivitySubtitle:
        "Lo que está ocurriendo en tus canales y agentes.",

      teamSubtitle:
        "Administra las personas que tienen acceso a tu organización.",
      teamInviteMember: "Invitar miembro",
      teamActiveMembers: "Miembros activos",
      teamAvailableSlots: "Cupos disponibles",
      teamPendingInvitations: "Invitaciones pendientes",
      teamCapacityNotice:
        "Tu plan no tiene cupos disponibles. Puedes enviar invitaciones, pero no podrán aceptarse hasta liberar un cupo o mejorar el plan.",
      teamActiveSection: "Miembros activos",
      teamInactiveSection: "Miembros inactivos",
      teamInvitations: "Invitaciones",
      teamRole: "Rol",
      teamAccess: "Acceso",
      teamRoleOwner: "Propietario",
      teamRoleManager: "Administrador",
      teamRoleOperator: "Operador",
      teamRoleAnalyst: "Analista",
      teamActive: "Activo",
      teamInactive: "Inactivo",
      teamAllStores: "Todas las tiendas",
      teamNoStores: "Sin tiendas asignadas",
      teamSelectedStores: "Tiendas específicas",
      teamStoreAccess: "Acceso a tiendas",
      teamStoreAccessHelp:
        "Define a qué tiendas podrá acceder este miembro.",
      teamEmail: "Correo electrónico",
      teamEmailRequired: "El correo es obligatorio.",
      teamStoreRequired:
        "Selecciona al menos una tienda.",
      teamSendInvitation: "Enviar invitación",
      teamSendingInvitation: "Enviando...",
      teamInvitationCreated:
        "Invitación creada correctamente.",
      teamInvitationCancelled:
        "Invitación cancelada.",
      teamInvitationHelp:
        "La invitación pendiente no consume un cupo. El cupo se valida cuando la persona acepta.",
      teamCancelInvitation: "Cancelar",
      teamNoPendingInvitations:
        "No hay invitaciones pendientes.",
      teamDeactivate: "Desactivar",
      teamReactivate: "Reactivar",
      teamMemberDeactivated:
        "Miembro desactivado.",
      teamMemberReactivated:
        "Miembro reactivado.",
      teamLoading: "Cargando equipo...",

      agentStatus: "Agentes IA",
      online: "Activo",
      salesAgent: "Agente de ventas",
      supportAgent: "Agente de soporte",
      ordersAgent: "Agente de pedidos",

      knowledgeStatus: "Bases de conocimiento",
      sourcesConnected: "fuentes conectadas",

      welcomeTitle: "Tu equipo de IA está listo.",
      welcomeText:
        "Conecta Shopify, WhatsApp y tus fuentes de conocimiento para comenzar a convertir conversaciones en ventas.",

      connectStore: "Conectar tienda",
      createAgent: "Crear agente",

      spanish: "ES",
      english: "EN",
      systemOnline: "Sistema operativo",

      conversationsTitle: "Conversaciones",
      conversationsSubtitle:
        "Gestiona WhatsApp, atención humana y agentes IA desde una sola bandeja.",

      searchConversation: "Buscar conversación...",
      all: "Todas",
      unread: "No leídas",
      aiManaged: "IA",
      humanManaged: "Humano",

      takeConversation: "Tomar conversación",
      returnToAI: "Devolver a IA",
      typeMessage: "Escribe un mensaje...",
      typeMessageWhatsApp:
        "Escribe un mensaje... (se enviará por WhatsApp)",
      autoReply: "Auto",
      send: "Enviar",

      customerInformation: "Información del cliente",
      customer: "Cliente",
      phone: "Teléfono",
      email: "Correo",
      country: "País",
      orders: "Pedidos",
      totalSpent: "Total comprado",

      currentAgent: "Agente actual",
      aiActive: "IA activa",
      humanActive: "Atención humana",

      shopify: "Shopify",
      connected: "Conectado",
      customerSince: "Cliente desde",
      lastOrder: "Último pedido",

      tags: "Etiquetas",
      highIntent: "Alta intención",
      returningCustomer: "Cliente recurrente",

      chatToday: "Hoy",
      aiThinking: "El agente IA está atendiendo esta conversación.",

      active: "Activo",
      workspace: "Espacio de trabajo",

      activityWhatsapp: "Nueva conversación · Cliente #1284",
      activityShopify: "Pedido #1042 creado por agente IA",
      activityKnowledge: "Base Productos consultada",
      activitySales:
        "Recomendación generada con inventario disponible",

      now: "ahora",

      commerceTabSummary: "Resumen",
      commerceTabProducts: "Productos",
      commerceTabOrders: "Órdenes",
      commerceSummaryError:
        "No se pudo cargar el resumen de comercio.",
      commerceNoData:
        "No hay datos de comercio disponibles.",
      commerceStatProducts: "Productos",
      commerceStatOrders: "Órdenes",
      commerceStatTotalValue: "Valor total",
      commerceStatusPending: "Pendientes",
      commerceStatusCreated: "Creadas",
      commerceStatusFailed: "Fallidas",
      commerceStatusUnknown: "Desconocido",
      commerceRecentOrders: "Órdenes recientes",
      commerceRecentProducts:
        "Productos recientes",
      commerceActive: "Activo",
      commerceInactive: "Inactivo",
      commerceProductsError:
        "No se pudieron cargar los productos.",
      commerceProductsSearch: "Buscar productos...",
      commerceSearch: "Buscar",
      commerceNoProducts:
        "No hay productos disponibles.",
      commerceResultsCount:
        "{{count}} producto(s)",
      commerceMore: "más",
      commerceOrdersError:
        "No se pudieron cargar las órdenes.",
      commerceNoOrders:
        "No hay órdenes disponibles.",
      commerceOrdersCount:
        "{{count}} orden(es)",
      commerceOrderNumber: "#",
      commerceOrderTotal: "Total",
      commerceOrderStatus: "Estado",
      commerceOrderSource: "Origen",
      commerceOrderDate: "Fecha",
      commerceOrderStatusFailed: "Fallida",
      commerceOrderStatusPending: "Pendiente",
      commerceOrderStatusCreated: "Creada",
      commerceOrderStatusUnknown: "Desconocido",
      commerceOrderStatusHistorical: "Histórica",

      autoTabRules: "Reglas",
      autoTabExecutions: "Ejecuciones",
      autoLoadError:
        "No se pudieron cargar las automatizaciones.",
      autoNoRules:
        "No hay reglas de automatización configuradas.",
      autoNewRule: "Nueva regla",
      autoEditRule: "Editar regla",
      autoNameRequired: "El nombre es obligatorio.",
      autoSaveError:
        "No se pudo guardar la automatización.",
      autoToggleError:
        "No se pudo cambiar el estado.",
      autoDeleteError:
        "No se pudo eliminar la automatización.",
      autoDeleteTitle: "Eliminar regla",
      autoDeleteConfirm:
        "¿Estás seguro de que deseas eliminar «{{name}}»? Esta acción no se puede deshacer.",
      autoDelete: "Eliminar",
      autoCancel: "Cancelar",
      autoSaveChanges: "Guardar cambios",
      autoCreate: "Crear",
      autoEdit: "Editar",
      autoToggle: "Activar/Desactivar",
      autoRun: "Ejecutar",
      autoRunNow: "Ejecutar ahora",
      autoConditions: "Condiciones",
      autoActions: "Acciones",
      autoLastRun: "Última ejecución",
      autoFormName: "Nombre",
      autoFormNamePlaceholder: "Ej: Nota automática",
      autoFormDescription: "Descripción",
      autoFormDescPlaceholder:
        "Descripción opcional",
      autoFormTrigger: "Disparador",
      autoFormConditions: "Condiciones",
      autoFormActions: "Acciones",
      autoFormActive: "Activo",
      autoFormValue: "Valor",
      autoFormLogMessage: "Mensaje",
      autoFormNoteText: "Texto de la nota",
      autoNoConditions:
        "Sin condiciones (se ejecuta siempre).",
      autoNoActions:
        "Sin acciones configuradas.",
      autoAddCondition: "Agregar condición",
      autoAddAction: "Agregar acción",
      autoRunPayload: "Payload (JSON)",
      autoRunResult: "Resultado",
      autoTrigger_manual: "Manual",
      autoTrigger_order_created: "Orden creada",
      autoTrigger_order_failed: "Orden fallida",
      autoTrigger_conversation_created:
        "Conversación creada",
      autoTrigger_message_received:
        "Mensaje recibido",
      autoAction_log_event: "Registrar evento",
      autoAction_add_order_note:
        "Agregar nota a orden",
      autoExecLoadError:
        "No se pudieron cargar las ejecuciones.",
      autoNoExecutions:
        "No hay ejecuciones registradas.",
      autoExecAutomation: "Automatización",
      autoExecEvent: "Evento",
      autoExecStatus: "Estado",
      autoExecStarted: "Inicio",
      autoExecDuration: "Duración",
      autoExecDetail: "Detalle de ejecución",
      autoExecError: "Error",
      autoExecInput: "Entrada",
      autoExecResult: "Resultado",
      autoClose: "Cerrar",
    },
  },

  en: {
    translation: {
      brandTagline: "Intelligent conversations for global commerce",

      overview: "Overview",
      plans: "Plans",

      plansTitle: "Plans",
      plansSubtitle:
        "Choose the capacity your operation needs. You can suspend stores without losing their data.",

      plansBillingEyebrow: "BILLING",
      plansChoosePayment: "Choose how you want to pay",
      plansPaymentHelp:
        "Pay for a longer period and get a better price.",

      plansRecommended: "Most popular",
      plansCurrentPlan: "Current plan",
      plansChoosePlan: "Choose plan",
      plansUpgrade: "Upgrade plan",
      plansDowngrade: "Change at renewal",

      plansMonthlyPrice: "Monthly price",
      plansPeriodPrice: "Period price",
      plansCurrentPeriod: "Current period",

      plansImmediateUpgrade: "Upgrade available now",
      plansCalculating: "Calculating...",
      plansCheckingProration:
        "Checking proration with Paddle",
      plansPayDifferenceToday:
        "You only pay the prorated difference today.",
      plansNextRenewalFullPrice:
        "On your next renewal, you'll be charged the full price of your new plan according to your billing period.",
      plansPriceUnavailable: "Price unavailable",
      plansProrationUnavailable:
        "We couldn't calculate the proration. Please try again.",

      plansActiveStore: "active store",
      plansActiveStores: "active stores",

      plansRenewalEyebrow: "RENEWAL",
      plansAutoRenewTitle: "Automatic renewal",
      plansAutoRenewEnabled: "Automatic renewal enabled",
      plansAutoRenewEnabledHelp:
        "Your plan will renew automatically at the end of the billing period.",
      plansAutoRenewHelp:
        "Keep your plan active without interruption. DIAGLOB will automatically renew your subscription at the end of each period.",
      plansAutoRenewDisabled:
        "Automatic renewal disabled",
      plansAutoRenewDisabledHelp:
        "Your plan will remain active until the paid period ends. After that, your stores will be suspended without deleting their data.",

      plansScheduledChange: "Scheduled change",
      plansScheduledChangeTitle: "Scheduled plan change",
      plansCanceling: "Canceling...",
      plansCancelChange: "Cancel change",
      plansNoActivePlan: "No active plan",
      plansNoActivePlanHelp:
        "Choose a plan to activate DIAGLOB features.",
      plansChangePeriodAtRenewal:
        "Change billing period at renewal",
      plansAvailableAtRenewal:
        "Available at renewal",
      plansOpeningPayment: "Opening checkout...",
      plansConfirmUpgrade: "Confirm upgrade",
      plansCurrentPlanLabel: "Current plan",
      plansNewPlanLabel: "New plan",
      plansPayToday: "You'll pay today",
      plansProrationExplanation:
        "Paddle automatically calculates the unused time on your current plan.",
      plansNewPlanProratedCharge:
        "Prorated charge for new plan",
      plansCurrentPlanCredit:
        "Current plan credit",
      plansNextRenewal:
        "Next renewal",
      plansCurrentPeriodLockedPrefix:
        "Your subscription keeps its current billing period of",
      plansCurrentPeriodLockedHelp:
        "Your billing period stays fixed while the subscription is active. When you change plans, you keep the same billing period.",
      plansDaysRemaining:
        "{{count}} days remaining",
      plansOneDayRemaining:
        "1 day remaining",
      plansRenewsToday:
        "Renews today",
      plansNextRenewalDate:
        "Next renewal: {{date}}",
      plansNextMonthlyPrice:
        "Next monthly price",
      plansPerMonthEquivalent:
        "per month",
      plansScheduling: "Scheduling...",
      plansScheduleForRenewal:
        "Schedule for renewal",

      mobileOpenMenu:
        "Open menu",
      mobileCloseMenu:
        "Close menu",
      mobileNavigation:
        "Main navigation",
      logout:
        "Sign out",
      lightMode:
        "Light mode",
      darkMode:
        "Dark mode",

      plansAutoRenewUpdateError:
        "We couldn't update automatic renewal.",
      plansPlanChangeError:
        "We couldn't process the plan change.",
      plansScheduledChangeCanceled:
        "The scheduled plan change was canceled.",
      plansScheduledChangeCancelError:
        "We couldn't cancel the scheduled change.",
      plansScheduledChangeSuccess:
        "Change scheduled successfully. You'll keep using your current plan until renewal.",
      plansCancelScheduledChange:
        "Cancel change",

      plansPeriodChangeError:
        "Your current plan is billed every {{currentPeriod}}. Changing to {{selectedPeriod}} can't be prorated. You must wait until the current billing period ends to apply the new plan and billing period.",
      plansChangeToConnector:
        "to",
      plansChangeDate:
        "Change date",
      plansProcessing:
        "Processing...",
      plansPlanChange:
        "Plan change",
      plansScheduleChangeTitle:
        "Schedule change at renewal",
      plansAdditionalChargeToday:
        "Additional charge today",
      plansKeepCurrentUntilRenewal:
        "You'll keep your current plan until renewal.",
      commonCancel:
        "Cancel",

      planRequiredDefault:
        "You need an active plan to perform this action.",
      noActiveStore:
        "No active store",
      selectStore:
        "Select a store",

      conversationsLoadError:
        "We couldn't load the conversations.",
      conversationLoadError:
        "We couldn't load the conversation.",
      conversationModeError:
        "We couldn't change the conversation mode.",
      conversationSendError:
        "We couldn't send the message.",

      plansMissingCheckoutUrl:
        "The checkout URL was not received.",
      plansPaddleNotReady:
        "Paddle isn't ready yet.",
      plansUpgradeError:
        "We couldn't complete the upgrade.",
      plansDowngradeScheduleError:
        "We couldn't schedule the plan change.",
      plansBillingPeriodLockedTitle:
        "The billing period remains unchanged while the subscription is active.",
      commonLoading:
        "Loading...",
      storeSingular:
        "store",
      storePlural:
        "stores",
      storeActive:
        "Active",
      storeSuspended:
        "Suspended",
      plansSelectActiveStores:
        "Select the stores that will remain active",
      plansSelectUpToStores:
        "You can select up to {{count}} {{stores}}",
      plansStoreActiveSince:
        "Active since {{date}}",
      plansDowngradeStoreSelectionHelp:
        "Your selection will only be applied at renewal. You may select active or suspended stores. Selected suspended stores will be activated when the new plan takes effect. If a selected store was deleted, DIAGLOB may replace it with an already active store, prioritizing the oldest active store.",
      plansNewStoreLimitHelp:
        "The new store limit will only apply when the new plan takes effect.",
      plansNoStoresSuspendedToday:
        "Scheduling this change does not suspend any stores today.",
      plansSuspendedStoresRenewalHelp:
        "Selected suspended stores will only be activated when the new plan takes effect. If a selection is deleted before renewal, DIAGLOB will use an already active store as a fallback.",

      loginI18nConfirmCodeHelp:
        "Enter the code Cognito sent to your email.",

      agentsI18nEmptyHelp:
        "Create the first AI agent for this organization.",

      loginI18nLoginError:
        "We couldn't sign you in.",
      loginI18nNameRequired:
        "Enter your name.",
      loginI18nOrganizationRequired:
        "Enter your company name.",
      loginI18nCreateError:
        "We couldn't create the account.",
      loginI18nConfirmError:
        "We couldn't confirm the account.",
      loginI18nCodeResent:
        "We sent a new code to your email.",
      loginI18nResendError:
        "We couldn't resend the code.",
      loginI18nSubtitle:
        "Sign in to manage your conversations and stores.",
      loginI18nEmail:
        "Email address",
      loginI18nPassword:
        "Password",
      loginI18nCreateNewAccount:
        "Create a new account",
      loginI18nCreateAccount:
        "Create account",
      loginI18nName:
        "Name",
      loginI18nPasswordHint:
        "Use a strong password that meets the policy configured in Cognito.",
      loginI18nConfirmEmailTitle:
        "Confirm your email",
      loginI18nSigningIn:
        "Signing in...",
      loginI18nSignIn:
        "Sign in",
      loginI18nCreating:
        "Creating...",
      loginI18nConfirming:
        "Confirming...",
      loginI18nConfirmAndEnter:
        "Confirm and sign in",
      loginI18nOrganizationPlaceholder:
        "e.g. Moda Express",

      agentsI18nLoadError:
        "We couldn't load the agent configuration.",
      agentsI18nNameRequired:
        "The agent needs a name.",
      agentsI18nRoleRequired:
        "The agent needs a role.",
      agentsI18nSaveError:
        "We couldn't save the agent.",
      agentsI18nStatusError:
        "We couldn't change the agent status.",
      agentsI18nSubtitle:
        "Manage the agents that serve your stores and their knowledge sources.",
      agentsI18nActive:
        "Active",
      agentsI18nInactive:
        "Inactive",
      agentsI18nStores:
        "Stores",
      agentsI18nNoStores:
        "No stores",
      agentsI18nEdit:
        "Edit",
      agentsI18nEditAgent:
        "Edit agent",
      agentsI18nNewAgent:
        "New agent",
      agentsI18nName:
        "Name",
      agentsI18nOrganization:
        "Organization",
      agentsI18nSelectedStores:
        "Selected stores",
      agentsI18nAgentActive:
        "Active agent",
      agentsI18nCancel:
        "Cancel",
      agentsI18nDeactivate:
        "Deactivate",
      agentsI18nActivate:
        "Activate",
      agentsI18nSaveChanges:
        "Save changes",
      agentsI18nCreateAgent:
        "Create agent",
      agentsI18nNamePlaceholder:
        "e.g. Colombia Sales",
      agentsI18nRolePlaceholder:
        "sales, support...",

      knowledgeI18nLoadError:
        "We couldn't load the Knowledge Bases.",
      knowledgeI18nNameRequired:
        "The Knowledge Base needs a name.",
      knowledgeI18nStoreRequired:
        "Select at least one store.",
      knowledgeI18nSaveError:
        "We couldn't save the Knowledge Base.",
      knowledgeI18nStatusError:
        "We couldn't change the status.",
      knowledgeI18nDocumentsLoadError:
        "We couldn't load the documents.",
      knowledgeI18nDocumentUploadError:
        "We couldn't upload the document.",
      knowledgeI18nDocumentDeleteError:
        "We couldn't delete the document.",

      knowledgeI18nNewKnowledgeBase:
        "New Knowledge Base",
      knowledgeI18nEditKnowledgeBase:
        "Edit Knowledge Base",
      knowledgeI18nWholeOrganization:
        "Entire organization",
      knowledgeI18nSelectedStores:
        "Selected stores",
      knowledgeI18nActive:
        "Active",
      knowledgeI18nInactive:
        "Inactive",
      knowledgeI18nStores:
        "Stores",
      knowledgeI18nAllStores:
        "All stores",
      knowledgeI18nPendingBedrock:
        "Waiting to connect to Bedrock",
      knowledgeI18nDeactivate:
        "Deactivate",
      knowledgeI18nActivate:
        "Activate",
      knowledgeI18nName:
        "Name",
      knowledgeI18nNamePlaceholder:
        "e.g. Return policies",
      knowledgeI18nBedrockPlaceholder:
        "Assigned when Bedrock is connected",
      knowledgeI18nKnowledgeBaseActive:
        "Active Knowledge Base",
      knowledgeI18nCancel:
        "Cancel",
      knowledgeI18nSaveChanges:
        "Save changes",
      knowledgeI18nCreateKnowledgeBase:
        "Create Knowledge Base",
      knowledgeI18nDeleteDocument:
        "Delete document",

      storesI18nLoadError:
        "We couldn't load the stores and markets.",
      storesI18nDeletedSuccess:
        "Store \"{{name}}\" was deleted.",
      storesI18nDeleteError:
        "We couldn't delete the store.",
      storesI18nNameRequired:
        "Enter the store name.",
      storesI18nCountryRequired:
        "Select a country or market.",
      storesI18nUpdatedSuccess:
        "Store updated successfully.",
      storesI18nCreatedSuccess:
        "Store created successfully.",
      storesI18nPlanLimitReached:
        "You've reached your plan's active store limit.",
      storesI18nSaveError:
        "We couldn't save the store.",

      storesI18nLoading:
        "Loading stores and markets...",
      storesI18nTitle:
        "Stores and markets",
      storesI18nNewStore:
        "New store",
      storesI18nActiveStores:
        "Active stores",
      storesI18nAvailableMarkets:
        "Available markets",
      storesI18nNoStores:
        "You don't have any stores yet",
      storesI18nCreateFirstStore:
        "Create first store",
      storesI18nEmptyHelp:
        "Create your first store and select the market where it will operate.",
      storesI18nDelete:
        "Delete",

      storesI18nSlotAvailable:
        "{{count}} slot available",
      storesI18nSlotsAvailable:
        "{{count}} slots available",

      storesI18nActive:
        "Active",
      storesI18nSuspended:
        "Suspended",
      storesI18nNotConnected:
        "Not connected",

      storesI18nPlanLimitEyebrow:
        "PLAN LIMIT",
      storesI18nPlanLimitHelp:
        "You can suspend an active store to free up a slot and activate another without losing products, customers, orders, or history.",
      storesI18nViewPlans:
        "View plans",

      storesI18nConfirmDeleteEyebrow:
        "CONFIRM DELETION",
      storesI18nDeleteStoreTitle:
        "Delete store?",
      storesI18nAboutToDelete:
        "You're about to delete",
      storesI18nDeleteWarning:
        "The store will no longer be active and will not appear in normal DIAGLOB operations.",
      storesI18nDeleting:
        "Deleting...",
      storesI18nConfirmDelete:
        "Yes, delete store",

      storesI18nConfigureStore:
        "Configure store",
      storesI18nCountryMarket:
        "Country / market",
      storesI18nSelectCountry:
        "Select a country",
      storesI18nMarketLockedHelp:
        "The market cannot be changed after the store is created.",
      storesI18nStoreName:
        "Store name",
      storesI18nNamePlaceholder:
        "e.g. Diaglob Peru",
      storesI18nStoreActive:
        "Active store",
      storesI18nOperational:
        "The store is operational.",
      storesI18nSuspendedHelp:
        "The store will be suspended. Its data, customers, orders, and history will not be deleted.",
      storesI18nMarket:
        "Market",
      storesI18nSaving:
        "Saving...",
      storesI18nSaveChanges:
        "Save changes",
      storesI18nCreateStore:
        "Create store",

      knowledgeI18nDeleteConfirm:
        "Delete {{name}}?",
      knowledgeI18nEdit:
        "Edit",

      storesI18nStores:
        "Stores",
      storesI18nCancel:
        "Cancel",

      integrationsTitle:
        "Integrations",
      integrationsLoading:
        "Loading integrations...",
      integrationsConnected:
        "Connected",
      integrationsDisconnected:
        "Disconnected",
      integrationsConnect:
        "Connect",
      integrationsDisconnect:
        "Disconnect",
      integrationsCopyWebhook:
        "Copy webhook",
      integrationsCopyVerifyToken:
        "Copy verify token",
      integrationsShopifyNoDomain:
        "No Shopify domain",
      integrationsShopifyConnectError:
        "Could not start the Shopify connection.",
      integrationsShopifyDisconnected:
        "Shopify disconnected.",
      integrationsShopifyTest:
        "Test connection",
      integrationsShopifyTestOk:
        "Connection verified successfully.",
      integrationsShopifyTestError:
        "Could not verify Shopify connection.",
      integrationsShopifySync:
        "Sync products",
      integrationsShopifySyncOk:
        "Products synced successfully.",
      integrationsShopifySyncError:
        "Could not sync products.",
      integrationsShopifyOrderCreate:
        "Create order",
      integrationsShopifyOrderCreateOk:
        "Order created successfully.",
      integrationsShopifyOrderCreateError:
        "Could not create the order.",
      integrationsShopifyOrderNoVariants:
        "Sync products first to create orders.",
      integrationsShopifyOrderOpenInvoice:
        "Open payment link",
      integrationsShopifyOrdersTitle:
        "Orders",
      integrationsShopifyOrderEmpty:
        "No orders yet.",
      integrationsDisconnectError:
        "Could not disconnect.",
      integrationsDropiTokenRequired:
        "Enter the Dropi token to connect.",
      integrationsDropiConnected:
        "Dropi connected.",
      integrationsDropiDisconnected:
        "Dropi disconnected.",
      integrationsDropiConnectError:
        "Could not connect Dropi.",
      integrationsDropiTokenPlaceholder:
        "Dropi token",
      integrationsCopyError:
        "Could not copy the webhook.",

      integrationsWhatsAppConnected:
        "WhatsApp connected.",
      integrationsWhatsAppDisconnected:
        "WhatsApp disconnected.",
      integrationsWhatsAppConnectError:
        "Could not connect WhatsApp.",
      integrationsWhatsAppFieldsRequired:
        "phone_number_id, business_account_id and access_token are required.",
      integrationsWhatsAppPhonePlaceholder:
        "Phone Number ID",
      integrationsWhatsAppBizPlaceholder:
        "Business Account ID",
      integrationsWhatsAppTokenPlaceholder:
        "WhatsApp Access Token",

      appI18nViewPlans:
        "View plans",
      appI18nChangeTheme:
        "Change theme",

      plansI18nScheduledBannerTitle:
        "Scheduled plan change",
      plansI18nYourPlanWillChangeFrom:
        "Your plan will change from",
      plansI18nKeepCurrentFeaturesUntilThen:
        "Until then, you'll keep all the features of your current plan.",
      plansI18nScheduledBadge:
        "Scheduled change",
      plansI18nChangeAtRenewal:
        "Change at renewal",
      plansI18nDowngradeRenewalHelp:
        "You keep your current plan until the paid period ends. No proration applies.",
      plansI18nNewPeriodAtRenewal:
        "New billing period at renewal",
      plansI18nPeriodChangeRenewalHelp:
        "The duration change will begin at your next renewal. No proration applies.",
      plansI18nAvailableAtRenewalTitle:
        "Change available at renewal",
      plansI18nPlanAndPeriodRenewalHelp:
        "The new plan and billing period can take effect when your current period ends. No proration applies.",
      plansI18nCancel:
        "Cancel",

      teamI18nUnexpectedError:
        "An unexpected error occurred.",

      loginI18nVerificationSent:
        "We sent a verification code to {{email}}.",
      loginI18nProvisionError:
        "We couldn't create your workspace.",

      billingI18nUnitMonth:
        "month",
      billingI18nUnitMonths:
        "{{count}} months",
      billingI18nUnitYear:
        "year",

      appI18nPlanRequiredEyebrow:
        "PLAN REQUIRED",
      appI18nPlanRequiredTitle:
        "You don't have an active plan",

      billing1Month: "1 month",
      billing3Months: "3 months",
      billing6Months: "6 months",
      billing12Months: "12 months",

      billingPerMonth: "month",
      billingPerYear: "year",

      billingSave5: "Save 5%",
      billingSave10: "Save 10%",
      billingSave2Months: "Save 2 months",

      starterDescription:
        "For getting started with automated selling.",
      starterFeature1: "1 active store",
      starterFeature2: "Up to 1,000 customers/month",
      starterFeature3: "2 team members",
      starterFeature4: "Multi-agent WhatsApp",
      starterFeature5: "Basic automations",
      starterFeature6: "Shopify integration",

      growthDescription:
        "For businesses starting to scale.",
      growthFeature1: "2 active stores",
      growthFeature2: "Up to 5,000 customers/month",
      growthFeature3: "5 team members",
      growthFeature4: "AI for sales",
      growthFeature5: "Cart recovery",
      growthFeature6: "Customer segmentation",

      proDescription:
        "For multi-store and multi-country operations.",
      proFeature1: "3 active stores",
      proFeature2: "Up to 10,000 customers/month",
      proFeature3: "10 team members",
      proFeature4: "Advanced AI agents",
      proFeature5: "Advanced analytics",
      proFeature6: "Advanced automations",

      scaleDescription:
        "For high-volume operations.",
      scaleFeature1: "5 active stores",
      scaleFeature2: "Up to 25,000 customers/month",
      scaleFeature3: "15 team members",
      scaleFeature4: "Multi-country operations",
      scaleFeature5: "Priority support",
      scaleFeature6: "Advanced commerce features",

      conversations: "Conversations",
      customers: "Customers",
      team: "Team",
      agents: "AI Agents",
      knowledge: "Knowledge",
      commerce: "Commerce",
      automations: "Automations",
      analytics: "Analytics",
      settings: "Settings",

      dashboardTitle: "Operations center",
      dashboardSubtitle:
        "Manage conversations, agents and knowledge from one place.",

      activeConversations: "Active conversations",
      aiResolved: "Resolved by AI",
      conversionRate: "Conversion",
      revenueInfluenced: "Assisted sales",

      liveActivity: "Recent activity",
      liveActivitySubtitle:
        "What is happening across your channels and agents.",

      teamSubtitle:
        "Manage the people who have access to your organization.",
      teamInviteMember: "Invite member",
      teamActiveMembers: "Active members",
      teamAvailableSlots: "Available seats",
      teamPendingInvitations: "Pending invitations",
      teamCapacityNotice:
        "Your plan has no available seats. You can send invitations, but they cannot be accepted until a seat is freed or the plan is upgraded.",
      teamActiveSection: "Active members",
      teamInactiveSection: "Inactive members",
      teamInvitations: "Invitations",
      teamRole: "Role",
      teamAccess: "Access",
      teamRoleOwner: "Owner",
      teamRoleManager: "Administrator",
      teamRoleOperator: "Operator",
      teamRoleAnalyst: "Analyst",
      teamActive: "Active",
      teamInactive: "Inactive",
      teamAllStores: "All stores",
      teamNoStores: "No stores assigned",
      teamSelectedStores: "Selected stores",
      teamStoreAccess: "Store access",
      teamStoreAccessHelp:
        "Choose which stores this member can access.",
      teamEmail: "Email address",
      teamEmailRequired: "Email is required.",
      teamStoreRequired:
        "Select at least one store.",
      teamSendInvitation: "Send invitation",
      teamSendingInvitation: "Sending...",
      teamInvitationCreated:
        "Invitation created successfully.",
      teamInvitationCancelled:
        "Invitation cancelled.",
      teamInvitationHelp:
        "A pending invitation does not consume a seat. Capacity is checked when the person accepts.",
      teamCancelInvitation: "Cancel",
      teamNoPendingInvitations:
        "There are no pending invitations.",
      teamDeactivate: "Deactivate",
      teamReactivate: "Reactivate",
      teamMemberDeactivated:
        "Member deactivated.",
      teamMemberReactivated:
        "Member reactivated.",
      teamLoading: "Loading team...",

      agentStatus: "AI Agents",
      online: "Active",
      salesAgent: "Sales agent",
      supportAgent: "Support agent",
      ordersAgent: "Orders agent",

      knowledgeStatus: "Knowledge bases",
      sourcesConnected: "connected sources",

      welcomeTitle: "Your AI team is ready.",
      welcomeText:
        "Connect Shopify, WhatsApp and your knowledge sources to start turning conversations into sales.",

      connectStore: "Connect store",
      createAgent: "Create agent",

      spanish: "ES",
      english: "EN",
      systemOnline: "System operational",

      conversationsTitle: "Conversations",
      conversationsSubtitle:
        "Manage WhatsApp, human support and AI agents from one inbox.",

      searchConversation: "Search conversation...",
      all: "All",
      unread: "Unread",
      aiManaged: "AI",
      humanManaged: "Human",

      takeConversation: "Take conversation",
      returnToAI: "Return to AI",
      typeMessage: "Type a message...",
      typeMessageWhatsApp:
        "Type a message... (will be sent via WhatsApp)",
      autoReply: "Auto",
      send: "Send",

      customerInformation: "Customer information",
      customer: "Customer",
      phone: "Phone",
      email: "Email",
      country: "Country",
      orders: "Orders",
      totalSpent: "Total spent",

      currentAgent: "Current agent",
      aiActive: "AI active",
      humanActive: "Human support",

      shopify: "Shopify",
      connected: "Connected",
      customerSince: "Customer since",
      lastOrder: "Last order",

      tags: "Tags",
      highIntent: "High intent",
      returningCustomer: "Returning customer",

      chatToday: "Today",
      aiThinking: "The AI agent is handling this conversation.",

      active: "Active",
      workspace: "Workspace",

      activityWhatsapp: "New conversation · Customer #1284",
      activityShopify: "Order #1042 created by AI agent",
      activityKnowledge: "Products knowledge base queried",
      activitySales:
        "Recommendation generated with available inventory",

      now: "now",

      commerceTabSummary: "Summary",
      commerceTabProducts: "Products",
      commerceTabOrders: "Orders",
      commerceSummaryError:
        "Could not load commerce summary.",
      commerceNoData:
        "No commerce data available.",
      commerceStatProducts: "Products",
      commerceStatOrders: "Orders",
      commerceStatTotalValue: "Total value",
      commerceStatusPending: "Pending",
      commerceStatusCreated: "Created",
      commerceStatusFailed: "Failed",
      commerceStatusUnknown: "Unknown",
      commerceRecentOrders: "Recent orders",
      commerceRecentProducts: "Recent products",
      commerceActive: "Active",
      commerceInactive: "Inactive",
      commerceProductsError:
        "Could not load products.",
      commerceProductsSearch: "Search products...",
      commerceSearch: "Search",
      commerceNoProducts:
        "No products available.",
      commerceResultsCount:
        "{{count}} product(s)",
      commerceMore: "more",
      commerceOrdersError:
        "Could not load orders.",
      commerceNoOrders:
        "No orders available.",
      commerceOrdersCount:
        "{{count}} order(s)",
      commerceOrderNumber: "#",
      commerceOrderTotal: "Total",
      commerceOrderStatus: "Status",
      commerceOrderSource: "Source",
      commerceOrderDate: "Date",
      commerceOrderStatusFailed: "Failed",
      commerceOrderStatusPending: "Pending",
      commerceOrderStatusCreated: "Created",
      commerceOrderStatusUnknown: "Unknown",
      commerceOrderStatusHistorical: "Historical",

      autoTabRules: "Rules",
      autoTabExecutions: "Executions",
      autoLoadError:
        "Could not load automations.",
      autoNoRules:
        "No automation rules configured.",
      autoNewRule: "New rule",
      autoEditRule: "Edit rule",
      autoNameRequired: "Name is required.",
      autoSaveError:
        "Could not save automation.",
      autoToggleError:
        "Could not change status.",
      autoDeleteError:
        "Could not delete automation.",
      autoDeleteTitle: "Delete rule",
      autoDeleteConfirm:
        'Are you sure you want to delete "{{name}}"? This action cannot be undone.',
      autoDelete: "Delete",
      autoCancel: "Cancel",
      autoSaveChanges: "Save changes",
      autoCreate: "Create",
      autoEdit: "Edit",
      autoToggle: "Enable/Disable",
      autoRun: "Run",
      autoRunNow: "Run now",
      autoConditions: "Conditions",
      autoActions: "Actions",
      autoLastRun: "Last run",
      autoFormName: "Name",
      autoFormNamePlaceholder:
        "e.g. Auto note",
      autoFormDescription: "Description",
      autoFormDescPlaceholder:
        "Optional description",
      autoFormTrigger: "Trigger",
      autoFormConditions: "Conditions",
      autoFormActions: "Actions",
      autoFormActive: "Active",
      autoFormValue: "Value",
      autoFormLogMessage: "Message",
      autoFormNoteText: "Note text",
      autoNoConditions:
        "No conditions (runs always).",
      autoNoActions:
        "No actions configured.",
      autoAddCondition: "Add condition",
      autoAddAction: "Add action",
      autoRunPayload: "Payload (JSON)",
      autoRunResult: "Result",
      autoTrigger_manual: "Manual",
      autoTrigger_order_created: "Order created",
      autoTrigger_order_failed: "Order failed",
      autoTrigger_conversation_created:
        "Conversation created",
      autoTrigger_message_received:
        "Message received",
      autoAction_log_event: "Log event",
      autoAction_add_order_note:
        "Add order note",
      autoExecLoadError:
        "Could not load executions.",
      autoNoExecutions:
        "No executions recorded.",
      autoExecAutomation: "Automation",
      autoExecEvent: "Event",
      autoExecStatus: "Status",
      autoExecStarted: "Started",
      autoExecDuration: "Duration",
      autoExecDetail: "Execution detail",
      autoExecError: "Error",
      autoExecInput: "Input",
      autoExecResult: "Result",
      autoClose: "Close",
    },
  },
};

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: localStorage.getItem("diaglob-language") || "es",
    fallbackLng: "es",
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;
