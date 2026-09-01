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
      knowledgeI18nProvisioningPending:
        "Pendiente",
      knowledgeI18nProvisioningInProgress:
        "Aprovisionando",
      knowledgeI18nProvisioningReady:
        "Lista",
      knowledgeI18nProvisioningFailed:
        "Falló",
      knowledgeI18nRetryProvisioning:
        "Reintentar",
      knowledgeI18nProvisioningRetryError:
        "No fue posible reintentar el aprovisionamiento.",
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

      knowledgeGoogleDocuments:
        "DOCUMENTOS",
      knowledgeGoogleAddDocument:
        "Añadir documento",
      knowledgeGoogleAddDocumentFormats:
        "PDF, TXT, MD, HTML, DOC, DOCX, CSV, XLSX o Google Sheets.",
      knowledgeGoogleUploadFile:
        "Subir archivo",
      knowledgeGoogleNoDocuments:
        "Sin documentos",
      knowledgeGoogleNoDocumentsDescription:
        "Esta Knowledge Base todavía no tiene fuentes cargadas.",
      knowledgeGoogleConnected:
        "Conectado como",
      knowledgeGoogleNotConnected:
        "Conecta tu cuenta de Google para sincronizar hojas de cálculo.",
      knowledgeGoogleConnect:
        "Conectar Google",
      knowledgeGoogleDisconnect:
        "Desconectar",
      knowledgeGoogleDisconnectConfirm:
        "¿Desconectar tu cuenta de Google? Las fuentes existentes seguirán disponibles pero no se sincronizarán automáticamente.",
      knowledgeGoogleDisconnectError:
        "No fue posible desconectar la cuenta de Google.",
      knowledgeGoogleConnectionError:
        "No fue posible iniciar la conexión con Google.",
      knowledgeGoogleSheetTitle:
        "Google Sheets",
      knowledgeGoogleSheetDescription:
        "Sincroniza hojas de cálculo de Google como fuentes de conocimiento.",
      knowledgeGoogleSelectSheet:
        "Seleccionar hoja",
      knowledgeGoogleSelectSpreadsheet:
        "Selecciona una hoja de cálculo",
      knowledgeGoogleSheetsLoadError:
        "No fue posible cargar las hojas de cálculo.",
      knowledgeGoogleTabsLoadError:
        "No fue posible cargar las pestañas.",
      knowledgeGoogleSelectTab:
        "Selecciona una pestaña",
      knowledgeGoogleNoSheets:
        "Sin hojas de cálculo",
      knowledgeGoogleNoSheetsDescription:
        "No se encontraron hojas de cálculo accesibles en tu cuenta de Google.",
      knowledgeGoogleNoTabs:
        "Sin pestañas",
      knowledgeGoogleNoTabsDescription:
        "Esta hoja de cálculo no tiene pestañas disponibles.",
      knowledgeGoogleAddSourceError:
        "No fue posible agregar la fuente de Google Sheets.",
      knowledgeGoogleSync:
        "Sincronizar",
      knowledgeGoogleSyncing:
        "Sincronizando…",
      knowledgeGoogleIndexing:
        "Indexando…",
      knowledgeGooglePartialFailed:
        "Sincronización parcial",
      knowledgeGoogleUploaded:
        "Cargado",
      knowledgeGoogleFailed:
        "Fallido",
      knowledgeGoogleSynced:
        "Sincronizado",
      knowledgeGoogleSyncError:
        "Error de sincronización",
      knowledgeGoogleSyncPending:
        "Pendiente",
      knowledgeGoogleSyncConfirm:
        "¿Solicitar una nueva sincronización de esta fuente?",
      knowledgeGoogleSyncSuccess:
        "Sincronización iniciada correctamente.",
      knowledgeGoogleWorkspaceTitle:
        "Google Workspace",
      knowledgeGoogleWorkspaceDescription:
        "Conecta documentos y archivos que tu equipo ya utiliza.",
      knowledgeGoogleDocs: "Google Docs",
      knowledgeGoogleDriveFile: "Archivo de Google Drive",
      knowledgeGoogleDriveFolder: "Carpeta de Google Drive",
      knowledgeGoogleSelectFile: "Selecciona un archivo",
      knowledgeGoogleSelectFolder: "Selecciona una carpeta",
      knowledgeGoogleSearchDrive: "Buscar en Google Drive",
      knowledgeGoogleDriveFilesLoadError:
        "No fue posible cargar los archivos de Google Drive.",
      knowledgeGoogleDriveFoldersLoadError:
        "No fue posible cargar las carpetas de Google Drive.",
      knowledgeGoogleLoadMore: "Cargar más",
      knowledgeGoogleNoDriveFiles: "Sin archivos compatibles",
      knowledgeGoogleNoDriveFolders: "Sin carpetas",
      knowledgeGoogleAddDoc: "Agregar documento",
      knowledgeGoogleAddFile: "Agregar archivo",
      knowledgeGoogleAddFolder: "Agregar carpeta",
      knowledgeGoogleSyncFolder: "Sincronizar carpeta",
      knowledgeGoogleAdditionalPermissions:
        "Se necesitan permisos adicionales para usar Google Drive.",
      knowledgeGoogleExpandPermissions:
        "Ampliar permisos",
      knowledgeGoogleFresh: "Actualizado",
      knowledgeGoogleChanged: "Cambió",
      knowledgeGoogleStatic: "Estático",
      knowledgeGoogleDisconnected: "Desconectado",
      knowledgeGoogleLastModified: "Última modificación",
      knowledgeGoogleLastSynced: "Última sincronización",
      knowledgeGoogleFileCount: "{{count}} archivos",
      knowledgeGoogleClose: "Cerrar",

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

      ciSegmentNew: "Nuevo",
      ciSegmentInterested: "Interesado",
      ciSegmentHighIntent: "Alta intención",
      ciSegmentBuyer: "Comprador",
      ciSegmentRepeatBuyer: "Recurrente",
      ciSegmentVip: "VIP",
      ciSegmentAtRisk: "En riesgo",
      ciSegmentInactive: "Inactivo",

      ciAll: "Todos",
      ciTotalCustomers: "Total clientes",
      ciNew: "Nuevos",
      ciHighIntent: "Alta intención",
      ciBuyers: "Compradores",
      ciRepeatBuyers: "Recurrentes",
      ciVip: "VIP",
      ciAtRisk: "En riesgo",
      ciInactive: "Inactivos",

      ciSearchPlaceholder: "Buscar por nombre, teléfono o email...",
      ciTableCustomer: "Cliente",
      ciTableSegment: "Segmento",
      ciTableStore: "Tienda",
      ciTableLastInteraction: "Última interacción",
      ciTableOrders: "Pedidos",
      ciTableSpend: "Gasto",
      ciTableLastPurchase: "Última compra",
      ciView: "Ver",
      ciLoading: "Cargando...",
      ciErrorLoading: "Error al cargar datos",
      ciNoCustomers: "No hay clientes",
      ciNoCustomersSub: "Las estadísticas aparecerán cuando se creen registros de clientes a partir de conversaciones o pedidos.",
      ciPageInfo: "Página {{page}} de {{total}}",

      ciToday: "Hoy",
      ciYesterday: "Ayer",
      ciDaysAgo: "hace {{count}} días",
      ciWeeksAgo: "hace {{count}} sem",
      ciMonthsAgo: "hace {{count}} meses",

      ciConversations: "Conversaciones",
      ciOrdersLabel: "Pedidos",
      ciLifetimeSpend: "Gasto total",
      ciLastInteraction: "Última interacción",
      ciLastPurchase: "Última compra",
      ciRecentOrders: "Pedidos recientes",
      ciRecentConversations: "Conversaciones recientes",

      ciTablePriority: "Prioridad",
      ciTableScore: "Score",
      ciTableHealth: "Estado",

      ciPriorityHigh: "Alta",
      ciPriorityMedium: "Media",
      ciPriorityLow: "Baja",

      ciHealthActive: "Activo",
      ciHealthAtRisk: "En riesgo",
      ciHealthInactive: "Inactivo",

      ciScore: "Customer Score",
      ciScoreExplain: "Puntuación de engagement comercial",
      ciOpportunities: "Oportunidades",
      ciRisks: "Riesgos",
      ciNextBestAction: "Siguiente accion recomendada",
      ciTimeline: "Cronologia de actividad",
      ciFailedOrders: "Pedidos fallidos",

      ciHighPriority: "Alta prioridad",
      ciNeedsFollowup: "Requiere seguimiento",

      ciFilterAllPriority: "Todas las prioridades",
      ciFilterAllHealth: "Todos los estados",

      ciActionFollowUp: "Seguimiento de conversacion",
      ciActionRecoverFailed: "Recuperar pedido fallido",
      ciActionReengage: "Reactivar cliente",
      ciActionReviewVip: "Revisar cliente VIP",
      ciActionNoAction: "Sin accion necesaria",

      ciTimelineCreated: "Cliente creado",
      ciTimelineConversation: "Conversacion",
      ciTimelineOrderCreated: "Pedido creado",
      ciTimelineOrderFailed: "Pedido con estado fallido",
      ciTimelineOrderUnknown: "Pedido con estado desconocido",
      ciTimelineOrderPending: "Pedido pendiente",

      ciCodeRecentInteraction: "Interaccion reciente",
      ciCodeModerateInteraction: "Interaccion moderada",
      ciCodeStaleInteraction: "Interaccion antigua",
      ciCodeMultipleConversations: "Multiples conversaciones",
      ciCodeHasConversations: "Tiene conversaciones",
      ciCodeHighMessageVolume: "Alto volumen de mensajes",
      ciCodeModerateMessageVolume: "Volumen moderado de mensajes",
      ciCodeVipCustomer: "Cliente VIP",
      ciCodeRepeatCustomer: "Cliente recurrente",
      ciCodeHasOrders: "Tiene pedidos",
      ciCodeRecentPurchase: "Compra reciente",
      ciCodeModeratePurchaseRecency: "Compra moderadamente reciente",
      ciCodeRecentPurchaseRecency: "Compra reciente",
      ciCodeLongTermCustomer: "Cliente a largo plazo",
      ciCodeEstablishedCustomer: "Cliente establecido",
      ciCodeHighOrderFrequency: "Alta frecuencia de pedidos",
      ciCodeRepeatBuyerLoyalty: "Comprador recurrente",
      ciCodeAtRisk: "Cliente en riesgo",
      ciCodeRecentFailedOrder: "Pedido reciente con error",
      ciCodeRecentUnknownOrder: "Pedido reciente desconocido",
      ciCodeVipAtRisk: "VIP en riesgo",
      ciCodeHighIntentStrongSignal: "Alta intencion con senal fuerte",
      ciCodeBuyerFailedOrderRecent: "Comprador con pedido fallido reciente",
      ciCodeRecentHighIntent: "Alta intencion reciente",
      ciCodeActiveBuyer: "Comprador activo",
      ciCodeHighEngagementScore: "Puntuacion de engagement alta",
      ciCodeInactiveCustomer: "Cliente inactivo",
      ciCodeLowEngagementScore: "Puntuacion de engagement baja",
      ciCodeNoPrioritySignal: "Sin senal de prioridad",
      ciCodeHighIntentNoOrder: "Alta intencion sin pedido",
      ciCodeRepeatCustomerOppo: "Oportunidad de cliente recurrente",
      ciCodeVipCustomerOppo: "Oportunidad de cliente VIP",
      ciCodeRecentFailedOrderRecovery: "Recuperacion de pedido fallido reciente",
      ciCodeRecentReengagement: "Reengagement reciente",
      ciCodeRecentConversationNoOrder: "Conversacion reciente sin pedido",
      ciCodeInactive: "Inactivo",
      ciCodeFailedOrder: "Pedido fallido",
      ciCodeUnknownOrder: "Pedido desconocido",
      ciCodeLongTimeSincePurchase: "Mucho tiempo desde la ultima compra",
      ciCodeLongTimeSinceInteraction: "Mucho tiempo desde la ultima interaccion",
      ciCodeNoEngagementHistory: "Sin historial de engagement",
      ciCodeOrderFailedRecently: "Pedido fallo recientemente",
      ciCodeVipCustomerAtRisk: "Cliente VIP en riesgo",
      ciCodeCustomerAtRisk: "Cliente en riesgo",
      ciCodeRecentHighIntentConversation: "Conversacion de alta intencion reciente",
      ciCodeBuyerBecomingInactive: "Comprador volviendose inactivo",
      ciCodeCustomerInactive: "Cliente inactivo",
      ciCodeNewCustomerNoEngagement: "Cliente nuevo sin engagement",
      ciCodeModeratelyRecentInteraction: "Interaccion moderadamente reciente",
      ciCodeStaleInteractionRecency: "Recencia de interaccion antigua",

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

      analyticsTabOverview: "General",
      analyticsTabConversations: "Conversaciones",
      analyticsTabCommerce: "Comercio",
      analyticsTabAutomations: "Automatizaciones",
      analyticsLoadError:
        "No se pudieron cargar las analíticas.",
      analyticsNoData:
        "No hay datos disponibles.",
      analyticsNoTimeseries:
        "No hay datos para el periodo seleccionado.",
      analyticsRangeAll: "Todo",
      analyticsRangeToday: "Hoy",
      analyticsRange7d: "7 días",
      analyticsRange30d: "30 días",
      analyticsRangeMonth: "Este mes",
      analyticsDateFrom: "Desde",
      analyticsDateTo: "Hasta",
      analyticsStatConversations: "Conversaciones",
      analyticsStatMessages: "Mensajes",
      analyticsStatProducts: "Productos",
      analyticsStatOrders: "Órdenes",
      analyticsStatOrderValue: "Valor de órdenes",
      analyticsStatActiveAutomations:
        "Automatizaciones activas",
      analyticsMessagesPerDay: "Mensajes por día",
      analyticsOrdersPerDay: "Órdenes por día",
      analyticsConversationsPerDay:
        "Conversaciones por día",
      analyticsExecutionsPerDay:
        "Ejecuciones por día",
      analyticsAvgMetrics: "Promedios",
      analyticsAvgMessagesPerConv:
        "Mensajes / conversación",
      analyticsAvgOrderValue: "Ticket promedio",
      analyticsAvgTicket: "Ticket promedio",
      analyticsAutomationRate:
        "Automatizaciones",
      analyticsExecutions: "Ejecuciones",
      analyticsSuccessRate: "Tasa de éxito",
      analyticsByChannel: "Por canal",
      analyticsByMode: "Por modo",
      analyticsSenderDistribution:
        "Distribución de remitentes",
      analyticsOrdersByStatus: "Por estado",
      analyticsOrdersBySource: "Por origen",
      analyticsHistorical: "Histórica",
      analyticsLocal: "Local",
      analyticsTopProducts: "Top productos",
      analyticsProduct: "Producto",
      analyticsUnits: "Unidades",
      analyticsValue: "Valor",
      analyticsTotalAutomations:
        "Total automatizaciones",
      analyticsActive: "Activas",
      analyticsExecutionsByStatus:
        "Ejecuciones por estado",
      analyticsExecutionsByTrigger:
        "Ejecuciones por trigger",
      analyticsAvgDuration:
        "Duración promedio",
      analyticsTopByExecutions:
        "Más ejecutadas",
      analyticsTopByFailures:
        "Más fallos",
      analyticsNoOrders:
        "No hay órdenes en este periodo.",

      landingNavProduct: "Producto",
      landingNavHow: "Cómo funciona",
      landingNavFeatures: "Funciones",
      landingNavIntegrations: "Integraciones",
      landingNavPricing: "Precios",
      landingNavFaq: "FAQ",
      landingNavLogin: "Iniciar sesión",
      landingNavRegister: "Crear cuenta",

      landingHeroEyebrow: "Plataforma de operaciones para ecommerce",
      landingHeroTitle: "Convierte tus conversaciones en una operación de ventas organizada.",
      landingHeroSubtitle: "Centraliza WhatsApp, automatiza tareas, gestiona pedidos y entiende qué está pasando en tus tiendas desde un solo lugar.",
      landingHeroCta: "Crear cuenta",
      landingHeroCtaSecondary: "Ver cómo funciona",
      landingHeroPricingNote: "Planes desde $19 USD/mes",

      landingProblemTitle: "Todo lo que necesitas para operar ventas por conversación.",
      landingProblem1: "Mensajes repartidos en múltiples chats",
      landingProblem2: "Respuestas tardías que pierden ventas",
      landingProblem3: "Pedidos difíciles de seguir",
      landingProblem4: "Tareas repetitivas que consumen tiempo",
      landingProblem5: "Varias tiendas completamente desconectadas",
      landingProblem6: "Poca claridad sobre qué está funcionando",
      landingProblemResolution: "Diaglob une todo.",

      landingHowTitle: "Cómo funciona",
      landingHowSubtitle: "Un flujo claro que conecta conversación con operación.",
      landingHowStep1Title: "Cliente escribe por WhatsApp",
      landingHowStep1Desc: "Un contacto te escribe con una consulta o pedido.",
      landingHowStep2Title: "Diaglob organiza y ayuda a responder",
      landingHowStep2Desc: "La conversación se registra y la IA responde o asiste automáticamente.",
      landingHowStep3Title: "Comercio y automatizaciones procesan",
      landingHowStep3Desc: "Productos, pedidos y reglas se vinculan a la conversación.",
      landingHowStep4Title: "Analytics muestra qué está pasando",
      landingHowStep4Desc: "Métricas en tiempo real de conversaciones, comercio y automatizaciones.",

      landingFeaturesTitle: "Todo en una sola plataforma",
      landingFeaturesSubtitle: "Módulos diseñados para que tu operación funcione de forma organizada.",
      landingFeatureConversationsTitle: "Conversaciones",
      landingFeatureConversationsDesc: "Centraliza conversaciones de WhatsApp en una sola vista con contexto completo.",
      landingFeatureAgentsTitle: "AI Agents",
      landingFeatureAgentsDesc: "Asistencia automática basada en configuración y conocimiento de tu negocio.",
      landingFeatureCommerceTitle: "Commerce",
      landingFeatureCommerceDesc: "Productos, variantes y pedidos conectados con tu conversación y Shopify.",
      landingFeatureAutomationsTitle: "Automations",
      landingFeatureAutomationsDesc: "Reglas que reaccionan a eventos como order.created o message.received.",
      landingFeatureAnalyticsTitle: "Analytics",
      landingFeatureAnalyticsDesc: "Métricas de conversaciones, comercio y automatizaciones en tiempo real.",
      landingFeatureOperationsTitle: "Operations Center",
      landingFeatureOperationsDesc: "Vista general de todo lo que necesita tu atención.",
      landingFeatureMultiStoreTitle: "Multi-store",
      landingFeatureMultiStoreDesc: "Administrar varias tiendas desde una sola organización.",
      landingFeatureTeamTitle: "Team",
      landingFeatureTeamDesc: "Roles y permisos para gestionar quién puede hacer qué.",

      landingWhatsappTitle: "WhatsApp, pero conectado a tu operación.",
      landingWhatsappDesc: "No solo recibes mensajes. Conectas WhatsApp con todo lo que importa.",
      landingWhatsapp1: "Recibir y responder conversaciones centralizadas",
      landingWhatsapp2: "Automatizar respuestas con AI Agents",
      landingWhatsapp3: "Asignar contexto de cliente y tienda",
      landingWhatsapp4: "Registrar actividad de cada interacción",
      landingWhatsapp5: "Medir tiempos de respuesta y resolución",
      landingWhatsapp6: "Conectar conversaciones con pedidos y productos",

      landingCommerceTitle: "Conecta conversación y comercio.",
      landingCommerceDesc: "Gestiona productos, variantes y pedidos sin perder el contexto de la conversación.",
      landingCommerce1: "Productos y variantes sincronizados desde Shopify",
      landingCommerce2: "Órdenes con estados created, pending, failed y unknown",
      landingCommerce3: "Shopify Draft Orders con idempotencia",
      landingCommerce4: "Búsqueda de comercio vinculada a conversaciones",
      landingCommerce5: "Actividad comercial visible en Operations Center",

      landingAutomationsTitle: "Automatiza lo que se repite.",
      landingAutomationsDesc: "Define reglas simples y deja que Diaglob ejecute acciones cuando ocurren eventos.",
      landingAutoTrigger1: "Cuando llega un mensaje",
      landingAutoAction1: "Ejecutar una acción automatizada",
      landingAutoTrigger2: "Cuando una orden se crea",
      landingAutoAction2: "Registrar seguimiento automáticamente",
      landingAutoTrigger3: "Cuando una orden falla",
      landingAutoAction3: "Activar una regla de notificación",

      landingAnalyticsTitle: "Entiende qué está pasando.",
      landingAnalyticsDesc: "Métricas reales de tu operación para tomar mejores decisiones.",
      landingAnalytics1: "Conversaciones: totales, activas, tiempo de respuesta",
      landingAnalytics2: "Mensajes: enviados, recibidos, por dirección",
      landingAnalytics3: "Órdenes: cantidad, valor promedio, tendencias",
      landingAnalytics4: "Top productos por volumen y valor",
      landingAnalytics5: "Automatizaciones: ejecuciones, tasa de éxito",
      landingAnalytics6: "Filtros por fecha y tienda",

      landingOperationsTitle: "Todo lo que necesita tu atención en una sola vista.",
      landingOperationsDesc: "El Operations Center agrega datos de todos tus módulos para que sepas qué necesita acción inmediata.",
      landingOperations1: "Conversaciones activas y pendientes",
      landingOperations2: "Órdenes recientes y su estado",
      landingOperations3: "Automatizaciones ejecutadas y fallidas",
      landingOperations4: "Estado de integraciones conectadas",
      landingOperations5: "Alertas de configuración incompleta",

      landingMultiStoreTitle: "Una cuenta. Varias tiendas.",
      landingMultiStoreDesc: "Administra múltiples tiendas desde una sola organización con datos separados y control centralizado.",
      landingMultiStore1: "Tiendas con configuraciones independientes",
      landingMultiStore2: "Conversaciones y pedidos separados por tienda",
      landingMultiStore3: "Permisos y roles por tienda",
      landingMultiStore4: "Commerce y WhatsApp por tienda",
      landingMultiStore5: "Analytics consolidado o por tienda",

      landingIntegrationsTitle: "Integraciones que conectan tu operación.",
      landingIntegrationsSubtitle: "Diaglob se conecta con las herramientas que ya usas.",
      landingIntegrationWhatsapp: "Conecta tu número de WhatsApp para recibir y responder mensajes.",
      landingIntegrationShopify: "Sincroniza productos, variantes y gestiona órdenes desde Diaglob.",
      landingIntegrationDropi: "Integración con Dropi para gestión de envíos y logística.",
      landingIntegrationAvailable: "Disponible",
      landingIntegrationComingSoon: "Próximamente",

      landingTargetTitle: "Construido para operaciones que venden por conversación.",
      landingTargetSubtitle: "Diaglob sirve para diferentes tipos de negocios que usan WhatsApp como canal de venta.",
      landingTargetEcommerceTitle: "Ecommerce",
      landingTargetEcommerceDesc: "Tiendas online que venden por WhatsApp y necesitan organizar la operación.",
      landingTargetDropshippingTitle: "Dropshipping",
      landingTargetDropshippingDesc: "Negocios que manejan múltiples proveedores y canales de venta.",
      landingTargetDtcTitle: "Marcas DTC",
      landingTargetDtcDesc: "Marcas que venden directo al consumidor y buscan personalizar la experiencia.",
      landingTargetWhatsappTitle: "Tiendas con WhatsApp",
      landingTargetWhatsappDesc: "Negocios que ya usan WhatsApp como canal principal de ventas.",
      landingTargetMultiStoreTitle: "Multi-tienda",
      landingTargetMultiStoreDesc: "Operaciones que manejan varias tiendas y necesitan visión centralizada.",

      landingBenefitsTitle: "Beneficios para tu operación.",
      landingBenefit1Title: "Responde más rápido",
      landingBenefit1Desc: "Centraliza conversaciones para que tu equipo responda sin perder contexto.",
      landingBenefit2Title: "Reduce trabajo repetitivo",
      landingBenefit2Desc: "Automatiza tareas que se ejecutan igual cada vez que ocurre un evento.",
      landingBenefit3Title: "Organiza pedidos",
      landingBenefit3Desc: "Gestiona órdenes conectadas a conversaciones con estados claros.",
      landingBenefit4Title: "Centraliza múltiples tiendas",
      landingBenefit4Desc: "Una sola vista para todas tus tiendas con datos separados.",
      landingBenefit5Title: "Detecta problemas antes",
      landingBenefit5Desc: "El Operations Center muestra alertas cuando algo necesita atención.",
      landingBenefit6Title: "Mide la operación",
      landingBenefit6Desc: "Analytics con métricas reales de conversaciones, comercio y automatizaciones.",

      landingFaqTitle: "Preguntas frecuentes",
      landingFaqSubtitle: "Resolvemos las dudas más comunes sobre Diaglob.",
      landingFaqWhatIs: "¿Qué es Diaglob?",
      landingFaqWhatIsAnswer: "Diaglob es una plataforma que centraliza WhatsApp, comercio, automatizaciones y analytics para que tu operación de ecommerce funcione de forma organizada.",
      landingFaqShopify: "¿Necesito Shopify para usar Diaglob?",
      landingFaqShopifyAnswer: "No. Shopify es una integración opcional. Puedes usar Diaglob con o sin Shopify. La integración te permite sincronizar productos y gestionar órdenes directamente.",
      landingFaqWhatsapp: "¿Funciona con WhatsApp?",
      landingFaqWhatsappAnswer: "Sí. Diaglob se conecta directamente con tu número de WhatsApp Business para recibir y responder conversaciones.",
      landingFaqMultiStore: "¿Puedo manejar varias tiendas?",
      landingFaqMultiStoreAnswer: "Sí. Diaglob soporta multi-tienda. Cada tienda tiene su propia configuración, conversaciones y datos, todo gestionado desde una sola organización.",
      landingFaqAi: "¿Qué puede hacer la IA?",
      landingFaqAiAnswer: "Los AI Agents pueden responder automáticamente configuraciones específicas de tu negocio, recomendar productos y resolver consultas frecuentes. Se configuran con reglas y conocimiento que tú defines.",
      landingFaqAutomations: "¿Qué son las automatizaciones?",
      landingFaqAutomationsAnswer: "Las automatizaciones son reglas que ejecutan acciones cuando ocurren eventos. Por ejemplo: cuando se crea una orden, registrar seguimiento automáticamente.",
      landingFaqMetrics: "¿Puedo ver métricas de mi operación?",
      landingFaqMetricsAnswer: "Sí. El módulo de Analytics muestra métricas de conversaciones, mensajes, órdenes, valor promedio, automatizaciones y top productos. También puedes filtrar por fecha y tienda.",
      landingFaqDropi: "¿Dropi ya está disponible?",
      landingFaqDropiAnswer: "Dropi está en proceso de integración. Actualmente se muestra como 'Próximamente'. Cuando la API oficial esté disponible, se activará automáticamente.",
      landingFaqPricing: "¿Cuánto cuesta?",
      landingFaqPricingAnswer: "Diaglob ofrece planes desde $19 USD/mes (Starter) hasta $179 USD/mes (Scale). Cada plan incluye diferentes cantidades de tiendas activas y funcionalidades.",
      landingFaqChangePlan: "¿Puedo cambiar de plan?",
      landingFaqChangePlanAnswer: "Sí. Puedes cambiar de plan en cualquier momento. Los upgrades se aplican de inmediato con prorrata. Los downgrades se aplican al renovar tu período actual.",
      landingFaqDataSeparation: "¿La información de cada tienda está separada?",
      landingFaqDataSeparationAnswer: "Sí. Cada tienda tiene sus propias conversaciones, productos, pedidos y configuraciones. Los datos nunca se mezclan entre tiendas dentro de la misma organización.",

      landingCtaFinalTitle: "Organiza hoy la operación que quieres escalar mañana.",
      landingCtaFinalSubtitle: "Crea tu cuenta gratis y empieza a centralizar tu operación.",
      landingCtaFinalButton: "Crear cuenta",

      landingFooterTagline: "Conversaciones, comercio y automatización para ecommerce.",
      landingFooterProduct: "Producto",
      landingFooterLegal: "Legal",
      landingFooterAccount: "Cuenta",
      landingFooterPrivacy: "Privacidad",
      landingFooterTerms: "Términos",
      landingFooterRights: "Todos los derechos reservados.",

      landingMockOverview: "Resumen",
      landingMockConversations: "Conversaciones",
      landingMockCommerce: "Commerce",
      landingMockAutomations: "Automations",
      landingMockAnalytics: "Analytics",
      landingMockResolved: "Resueltas",
      landingMockOrders: "Órdenes",

      themeSwitchLight: "Cambiar a modo claro",
      themeSwitchDark: "Cambiar a modo oscuro",

      landingSolution1: "Conversaciones centralizadas",
      landingSolution2: "Comercio conectado",
      landingSolution3: "Automatizaciones",
      landingSolution4: "Analytics + Operations",

      landingPricingTitle: "Planes simples, escalables",
      landingPricingSubtitle: "Elige el plan que mejor se adapte a tu operación.",
      landingPricingRecommended: "Recomendado",
      landingPricingMonth: "USD / mes",
      landingPricingStore: "tienda activa",
      landingPricingStores: "tiendas activas",
      landingPricingCta: "Empezar",

      landingPlanStarterFeature1: "1 tienda activa",
      landingPlanStarterFeature2: "Conversaciones WhatsApp",
      landingPlanStarterFeature3: "Commerce básico",
      landingPlanStarterFeature4: "Analytics esenciales",
      landingPlanStarterFeature5: "Soporte por correo",
      landingPlanStarterFeature6: "1 AI Agent",

      landingPlanGrowthFeature1: "2 tiendas activas",
      landingPlanGrowthFeature2: "Automatizaciones",
      landingPlanGrowthFeature3: "AI Agents avanzados",
      landingPlanGrowthFeature4: "Analytics completos",
      landingPlanGrowthFeature5: "Operations Center",
      landingPlanGrowthFeature6: "Soporte prioritario",

      landingPlanProFeature1: "3 tiendas activas",
      landingPlanProFeature2: "Todo de Growth",
      landingPlanProFeature3: "Multi-store completo",
      landingPlanProFeature4: "Team y permisos",
      landingPlanProFeature5: "Knowledge Bases",
      landingPlanProFeature6: "Soporte dedicado",

      landingPlanScaleFeature1: "5 tiendas activas",
      landingPlanScaleFeature2: "Todo de Pro",
      landingPlanScaleFeature3: "Capacidad máxima",
      landingPlanScaleFeature4: "Integraciones avanzadas",
      landingPlanScaleFeature5: "SLA garantizado",
      landingPlanScaleFeature6: "Onboarding personalizado",

      landingFooterFeatures: "Funciones",
      landingFooterIntegrations: "Integraciones",
      landingFooterPricing: "Precios",
      landingFooterLogin: "Iniciar sesión",
      landingFooterRegister: "Crear cuenta",

      landingBuiltTitle: "Conocimiento conectado. Operación multi-país.",
      landingBuiltSubtitle: "Diaglob une la información de tu negocio con una arquitectura preparada para múltiples tiendas y mercados.",

      landingKnowledgeLabel: "BASE DE CONOCIMIENTO",
      landingKnowledgeDesc: "Información centralizada y contextual para tus agentes.",
      landingKnowledgeHighlight: "Tu IA es tan buena como el conocimiento que tiene.",

      landingSourceGoogleSheets: "Google Sheets",
      landingSourceGoogleSheetsStatus: "Disponible",
      landingSourceGoogleSheetsDesc: "Conecta información que cambia constantemente.",
      landingSourceExcel: "Excel / CSV",
      landingSourceExcelStatus: "Disponible",
      landingSourceExcelDesc: "Sube archivos con productos, políticas o información de tu negocio.",
      landingSourceShopify: "Shopify",
      landingSourceShopifyStatus: "Disponible",
      landingSourceShopifyDesc: "Conecta los datos de productos de tu tienda con tu operación.",
      landingSourceDropi: "Dropi",
      landingSourceDropiStatus: "Próximamente",
      landingSourceDropiDesc: "Integración de catálogo y operación Dropi en preparación.",

      landingAgentLabel: "AGENTE DE IA",
      landingAgentDesc: "Responde usando el contexto real de tu negocio.",

      landingResultRespond: "Responde",
      landingResultRespondDesc: "Respuestas más relevantes con contexto.",
      landingResultRecommend: "Recomienda",
      landingResultRecommendDesc: "Productos con contexto real.",
      landingResultAutomate: "Automatiza",
      landingResultAutomateDesc: "Acciones basadas en información del negocio.",

      landingBuiltMultiTitle: "Varias tiendas. Varios mercados. Una sola operación.",
      landingBuiltMultiSubtitle: "Administra diferentes tiendas, mercados, monedas, idiomas e integraciones desde una sola plataforma.",

      landingStoreColombia: "Colombia",
      landingStoreMexico: "México",
      landingStoreUsa: "USA",
      landingStoreCurrencyCOP: "COP",
      landingStoreCurrencyMXN: "MXN",
      landingStoreCurrencyUSD: "USD",
      landingStoreLangEs: "ES",
      landingStoreLangEn: "EN",

      landingOpsCenter: "Operations Center",
      landingOpsCenterDesc: "Analytics, automatizations y equipo centralizados.",

      landingBuiltEachStore: "Cada tienda opera con su propio contexto, configuración e integraciones, mientras tú mantienes una visión central.",
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
      knowledgeI18nProvisioningPending:
        "Pending",
      knowledgeI18nProvisioningInProgress:
        "Provisioning",
      knowledgeI18nProvisioningReady:
        "Ready",
      knowledgeI18nProvisioningFailed:
        "Failed",
      knowledgeI18nRetryProvisioning:
        "Retry",
      knowledgeI18nProvisioningRetryError:
        "We couldn't retry provisioning.",
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

      knowledgeGoogleDocuments:
        "DOCUMENTS",
      knowledgeGoogleAddDocument:
        "Add document",
      knowledgeGoogleAddDocumentFormats:
        "PDF, TXT, MD, HTML, DOC, DOCX, CSV, XLSX or Google Sheets.",
      knowledgeGoogleUploadFile:
        "Upload file",
      knowledgeGoogleNoDocuments:
        "No documents",
      knowledgeGoogleNoDocumentsDescription:
        "This Knowledge Base has no sources uploaded yet.",
      knowledgeGoogleConnected:
        "Connected as",
      knowledgeGoogleNotConnected:
        "Connect your Google account to sync spreadsheets.",
      knowledgeGoogleConnect:
        "Connect Google",
      knowledgeGoogleDisconnect:
        "Disconnect",
      knowledgeGoogleDisconnectConfirm:
        "Disconnect your Google account? Existing sources will remain available but won't sync automatically.",
      knowledgeGoogleDisconnectError:
        "We couldn't disconnect your Google account.",
      knowledgeGoogleConnectionError:
        "We couldn't start the Google connection.",
      knowledgeGoogleSheetTitle:
        "Google Sheets",
      knowledgeGoogleSheetDescription:
        "Sync Google spreadsheets as knowledge sources.",
      knowledgeGoogleSelectSheet:
        "Select sheet",
      knowledgeGoogleSelectSpreadsheet:
        "Select a spreadsheet",
      knowledgeGoogleSheetsLoadError:
        "We couldn't load the spreadsheets.",
      knowledgeGoogleTabsLoadError:
        "We couldn't load the tabs.",
      knowledgeGoogleSelectTab:
        "Select a tab",
      knowledgeGoogleNoSheets:
        "No spreadsheets",
      knowledgeGoogleNoSheetsDescription:
        "No accessible spreadsheets found in your Google account.",
      knowledgeGoogleNoTabs:
        "No tabs",
      knowledgeGoogleNoTabsDescription:
        "This spreadsheet has no available tabs.",
      knowledgeGoogleAddSourceError:
        "We couldn't add the Google Sheets source.",
      knowledgeGoogleSync:
        "Sync",
      knowledgeGoogleSyncing:
        "Syncing…",
      knowledgeGoogleIndexing:
        "Indexing…",
      knowledgeGooglePartialFailed:
        "Partially failed",
      knowledgeGoogleUploaded:
        "Uploaded",
      knowledgeGoogleFailed:
        "Failed",
      knowledgeGoogleSynced:
        "Synced",
      knowledgeGoogleSyncError:
        "Sync error",
      knowledgeGoogleSyncPending:
        "Pending",
      knowledgeGoogleSyncConfirm:
        "Request a new sync for this source?",
      knowledgeGoogleSyncSuccess:
        "Sync started successfully.",
      knowledgeGoogleWorkspaceTitle:
        "Google Workspace",
      knowledgeGoogleWorkspaceDescription:
        "Connect documents and files your team already uses.",
      knowledgeGoogleDocs: "Google Docs",
      knowledgeGoogleDriveFile: "Google Drive File",
      knowledgeGoogleDriveFolder: "Google Drive Folder",
      knowledgeGoogleSelectFile: "Select a file",
      knowledgeGoogleSelectFolder: "Select a folder",
      knowledgeGoogleSearchDrive: "Search Google Drive",
      knowledgeGoogleDriveFilesLoadError:
        "We couldn't load the Google Drive files.",
      knowledgeGoogleDriveFoldersLoadError:
        "We couldn't load the Google Drive folders.",
      knowledgeGoogleLoadMore: "Load more",
      knowledgeGoogleNoDriveFiles: "No compatible files",
      knowledgeGoogleNoDriveFolders: "No folders",
      knowledgeGoogleAddDoc: "Add document",
      knowledgeGoogleAddFile: "Add file",
      knowledgeGoogleAddFolder: "Add folder",
      knowledgeGoogleSyncFolder: "Sync folder",
      knowledgeGoogleAdditionalPermissions:
        "Additional permissions are required to use Google Drive.",
      knowledgeGoogleExpandPermissions:
        "Expand permissions",
      knowledgeGoogleFresh: "Fresh",
      knowledgeGoogleChanged: "Changed",
      knowledgeGoogleStatic: "Static",
      knowledgeGoogleDisconnected: "Disconnected",
      knowledgeGoogleLastModified: "Last modified",
      knowledgeGoogleLastSynced: "Last synced",
      knowledgeGoogleFileCount: "{{count}} files",
      knowledgeGoogleClose: "Close",

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

      ciSegmentNew: "New",
      ciSegmentInterested: "Interested",
      ciSegmentHighIntent: "High intent",
      ciSegmentBuyer: "Buyer",
      ciSegmentRepeatBuyer: "Repeat buyer",
      ciSegmentVip: "VIP",
      ciSegmentAtRisk: "At risk",
      ciSegmentInactive: "Inactive",

      ciAll: "All",
      ciTotalCustomers: "Total customers",
      ciNew: "New",
      ciHighIntent: "High intent",
      ciBuyers: "Buyers",
      ciRepeatBuyers: "Repeat",
      ciVip: "VIP",
      ciAtRisk: "At risk",
      ciInactive: "Inactive",

      ciSearchPlaceholder: "Search by name, phone or email...",
      ciTableCustomer: "Customer",
      ciTableSegment: "Segment",
      ciTableStore: "Store",
      ciTableLastInteraction: "Last interaction",
      ciTableOrders: "Orders",
      ciTableSpend: "Spend",
      ciTableLastPurchase: "Last purchase",
      ciView: "View",
      ciLoading: "Loading...",
      ciErrorLoading: "Error loading data",
      ciNoCustomers: "No customers yet",
      ciNoCustomersSub: "Customer statistics will appear here when conversations or orders create customer records.",
      ciPageInfo: "Page {{page}} of {{total}}",

      ciToday: "Today",
      ciYesterday: "Yesterday",
      ciDaysAgo: "{{count}} days ago",
      ciWeeksAgo: "{{count}} weeks ago",
      ciMonthsAgo: "{{count}} months ago",

      ciConversations: "Conversations",
      ciOrdersLabel: "Orders",
      ciLifetimeSpend: "Lifetime spend",
      ciLastInteraction: "Last interaction",
      ciLastPurchase: "Last purchase",
      ciRecentOrders: "Recent orders",
      ciRecentConversations: "Recent conversations",

      ciTablePriority: "Priority",
      ciTableScore: "Score",
      ciTableHealth: "Health",

      ciPriorityHigh: "High",
      ciPriorityMedium: "Medium",
      ciPriorityLow: "Low",

      ciHealthActive: "Active",
      ciHealthAtRisk: "At risk",
      ciHealthInactive: "Inactive",

      ciScore: "Customer Score",
      ciScoreExplain: "Commercial engagement score",
      ciOpportunities: "Opportunities",
      ciRisks: "Risks",
      ciNextBestAction: "Next best action",
      ciTimeline: "Activity timeline",
      ciFailedOrders: "Failed orders",

      ciHighPriority: "High priority",
      ciNeedsFollowup: "Needs follow-up",

      ciFilterAllPriority: "All priorities",
      ciFilterAllHealth: "All health states",

      ciActionFollowUp: "Follow up conversation",
      ciActionRecoverFailed: "Recover failed order",
      ciActionReengage: "Re-engage customer",
      ciActionReviewVip: "Review VIP customer",
      ciActionNoAction: "No action needed",

      ciTimelineCreated: "Customer created",
      ciTimelineConversation: "Conversation",
      ciTimelineOrderCreated: "Order created",
      ciTimelineOrderFailed: "Order currently marked failed",
      ciTimelineOrderUnknown: "Order currently marked unknown",
      ciTimelineOrderPending: "Order pending",

      ciCodeRecentInteraction: "Recent interaction",
      ciCodeModerateInteraction: "Moderate interaction",
      ciCodeStaleInteraction: "Stale interaction",
      ciCodeMultipleConversations: "Multiple conversations",
      ciCodeHasConversations: "Has conversations",
      ciCodeHighMessageVolume: "High message volume",
      ciCodeModerateMessageVolume: "Moderate message volume",
      ciCodeVipCustomer: "VIP customer",
      ciCodeRepeatCustomer: "Repeat customer",
      ciCodeHasOrders: "Has orders",
      ciCodeRecentPurchase: "Recent purchase",
      ciCodeModeratePurchaseRecency: "Moderate purchase recency",
      ciCodeRecentPurchaseRecency: "Recent purchase recency",
      ciCodeLongTermCustomer: "Long-term customer",
      ciCodeEstablishedCustomer: "Established customer",
      ciCodeHighOrderFrequency: "High order frequency",
      ciCodeRepeatBuyerLoyalty: "Repeat buyer loyalty",
      ciCodeAtRisk: "Customer at risk",
      ciCodeRecentFailedOrder: "Recent failed order",
      ciCodeRecentUnknownOrder: "Recent unknown order",
      ciCodeVipAtRisk: "VIP at risk",
      ciCodeHighIntentStrongSignal: "High intent with strong signal",
      ciCodeBuyerFailedOrderRecent: "Buyer with recent failed order",
      ciCodeRecentHighIntent: "Recent high intent",
      ciCodeActiveBuyer: "Active buyer",
      ciCodeHighEngagementScore: "High engagement score",
      ciCodeInactiveCustomer: "Inactive customer",
      ciCodeLowEngagementScore: "Low engagement score",
      ciCodeNoPrioritySignal: "No priority signal",
      ciCodeHighIntentNoOrder: "High intent without an order",
      ciCodeRepeatCustomerOppo: "Repeat customer opportunity",
      ciCodeVipCustomerOppo: "VIP customer opportunity",
      ciCodeRecentFailedOrderRecovery: "Recent failed order recovery",
      ciCodeRecentReengagement: "Recent re-engagement",
      ciCodeRecentConversationNoOrder: "Recent conversation no order",
      ciCodeInactive: "Inactive",
      ciCodeFailedOrder: "Failed order",
      ciCodeUnknownOrder: "Unknown order",
      ciCodeLongTimeSincePurchase: "Long time since last purchase",
      ciCodeLongTimeSinceInteraction: "Long time since last interaction",
      ciCodeNoEngagementHistory: "No engagement history",
      ciCodeOrderFailedRecently: "Order failed recently",
      ciCodeVipCustomerAtRisk: "VIP customer at risk",
      ciCodeCustomerAtRisk: "Customer at risk",
      ciCodeRecentHighIntentConversation: "Recent high intent conversation",
      ciCodeBuyerBecomingInactive: "Buyer becoming inactive",
      ciCodeCustomerInactive: "Customer inactive",
      ciCodeNewCustomerNoEngagement: "New customer no engagement",
      ciCodeModeratelyRecentInteraction: "Moderately recent interaction",
      ciCodeStaleInteractionRecency: "Stale interaction recency",

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

      analyticsTabOverview: "Overview",
      analyticsTabConversations: "Conversations",
      analyticsTabCommerce: "Commerce",
      analyticsTabAutomations: "Automations",
      analyticsLoadError:
        "Could not load analytics.",
      analyticsNoData:
        "No data available.",
      analyticsNoTimeseries:
        "No data for the selected period.",
      analyticsRangeAll: "All",
      analyticsRangeToday: "Today",
      analyticsRange7d: "7 days",
      analyticsRange30d: "30 days",
      analyticsRangeMonth: "This month",
      analyticsDateFrom: "From",
      analyticsDateTo: "To",
      analyticsStatConversations: "Conversations",
      analyticsStatMessages: "Messages",
      analyticsStatProducts: "Products",
      analyticsStatOrders: "Orders",
      analyticsStatOrderValue: "Order value",
      analyticsStatActiveAutomations:
        "Active automations",
      analyticsMessagesPerDay: "Messages per day",
      analyticsOrdersPerDay: "Orders per day",
      analyticsConversationsPerDay:
        "Conversations per day",
      analyticsExecutionsPerDay:
        "Executions per day",
      analyticsAvgMetrics: "Averages",
      analyticsAvgMessagesPerConv:
        "Messages / conversation",
      analyticsAvgOrderValue: "Avg order value",
      analyticsAvgTicket: "Avg ticket",
      analyticsAutomationRate: "Automations",
      analyticsExecutions: "Executions",
      analyticsSuccessRate: "Success rate",
      analyticsByChannel: "By channel",
      analyticsByMode: "By mode",
      analyticsSenderDistribution:
        "Sender distribution",
      analyticsOrdersByStatus: "By status",
      analyticsOrdersBySource: "By source",
      analyticsHistorical: "Historical",
      analyticsLocal: "Local",
      analyticsTopProducts: "Top products",
      analyticsProduct: "Product",
      analyticsUnits: "Units",
      analyticsValue: "Value",
      analyticsTotalAutomations:
        "Total automations",
      analyticsActive: "Active",
      analyticsExecutionsByStatus:
        "Executions by status",
      analyticsExecutionsByTrigger:
        "Executions by trigger",
      analyticsAvgDuration: "Avg duration",
      analyticsTopByExecutions:
        "Most executed",
      analyticsTopByFailures:
        "Most failures",
      analyticsNoOrders:
        "No orders in this period.",

      landingNavProduct: "Product",
      landingNavHow: "How it works",
      landingNavFeatures: "Features",
      landingNavIntegrations: "Integrations",
      landingNavPricing: "Pricing",
      landingNavFaq: "FAQ",
      landingNavLogin: "Sign in",
      landingNavRegister: "Create account",

      landingHeroEyebrow: "Operations platform for ecommerce",
      landingHeroTitle: "Turn your conversations into an organized sales operation.",
      landingHeroSubtitle: "Centralize WhatsApp, automate tasks, manage orders and understand what's happening across your stores from one place.",
      landingHeroCta: "Create account",
      landingHeroCtaSecondary: "See how it works",
      landingHeroPricingNote: "Plans from $19 USD/month",

      landingProblemTitle: "Everything you need to run conversational sales.",
      landingProblem1: "Messages scattered across multiple chats",
      landingProblem2: "Slow responses that lose sales",
      landingProblem3: "Orders hard to track",
      landingProblem4: "Repetitive tasks that waste time",
      landingProblem5: "Multiple stores completely disconnected",
      landingProblem6: "Little clarity on what's working",
      landingProblemResolution: "Diaglob brings it all together.",

      landingHowTitle: "How it works",
      landingHowSubtitle: "A clear flow that connects conversation with operations.",
      landingHowStep1Title: "Customer writes on WhatsApp",
      landingHowStep1Desc: "A contact messages you with a question or order.",
      landingHowStep2Title: "Diaglob organizes and helps respond",
      landingHowStep2Desc: "The conversation is logged and AI responds or assists automatically.",
      landingHowStep3Title: "Commerce and automations process",
      landingHowStep3Desc: "Products, orders and rules are linked to the conversation.",
      landingHowStep4Title: "Analytics shows what's happening",
      landingHowStep4Desc: "Real-time metrics for conversations, commerce and automations.",

      landingFeaturesTitle: "Everything you need in one platform",
      landingFeaturesSubtitle: "Modules designed to keep your operation running smoothly.",
      landingFeatureConversationsTitle: "Conversations",
      landingFeatureConversationsDesc: "Centralize WhatsApp conversations in a single view with full context.",
      landingFeatureAgentsTitle: "AI Agents",
      landingFeatureAgentsDesc: "Automatic assistance based on your business configuration and knowledge.",
      landingFeatureCommerceTitle: "Commerce",
      landingFeatureCommerceDesc: "Products, variants and orders connected to your conversation and Shopify.",
      landingFeatureAutomationsTitle: "Automations",
      landingFeatureAutomationsDesc: "Rules that react to events like order.created or message.received.",
      landingFeatureAnalyticsTitle: "Analytics",
      landingFeatureAnalyticsDesc: "Real-time metrics for conversations, commerce and automations.",
      landingFeatureOperationsTitle: "Operations Center",
      landingFeatureOperationsDesc: "Overview of everything that needs your attention.",
      landingFeatureMultiStoreTitle: "Multi-store",
      landingFeatureMultiStoreDesc: "Manage multiple stores from a single organization.",
      landingFeatureTeamTitle: "Team",
      landingFeatureTeamDesc: "Roles and permissions to manage who can do what.",

      landingWhatsappTitle: "WhatsApp, but connected to your operation.",
      landingWhatsappDesc: "It's not just about receiving messages. You connect WhatsApp with everything that matters.",
      landingWhatsapp1: "Receive and respond to centralized conversations",
      landingWhatsapp2: "Automate responses with AI Agents",
      landingWhatsapp3: "Assign customer and store context",
      landingWhatsapp4: "Log activity from every interaction",
      landingWhatsapp5: "Measure response and resolution times",
      landingWhatsapp6: "Connect conversations with orders and products",

      landingCommerceTitle: "Connect conversation and commerce.",
      landingCommerceDesc: "Manage products, variants and orders without losing conversation context.",
      landingCommerce1: "Products and variants synced from Shopify",
      landingCommerce2: "Orders with created, pending, failed and unknown statuses",
      landingCommerce3: "Shopify Draft Orders with idempotency",
      landingCommerce4: "Commerce search linked to conversations",
      landingCommerce5: "Commercial activity visible in Operations Center",

      landingAutomationsTitle: "Automate what repeats.",
      landingAutomationsDesc: "Define simple rules and let Diaglob execute actions when events occur.",
      landingAutoTrigger1: "When a message arrives",
      landingAutoAction1: "Run an automated action",
      landingAutoTrigger2: "When an order is created",
      landingAutoAction2: "Log follow-up automatically",
      landingAutoTrigger3: "When an order fails",
      landingAutoAction3: "Trigger a notification rule",

      landingAnalyticsTitle: "Understand what's happening.",
      landingAnalyticsDesc: "Real metrics from your operation to make better decisions.",
      landingAnalytics1: "Conversations: totals, active, response time",
      landingAnalytics2: "Messages: sent, received, by direction",
      landingAnalytics3: "Orders: count, average value, trends",
      landingAnalytics4: "Top products by volume and value",
      landingAnalytics5: "Automations: executions, success rate",
      landingAnalytics6: "Filters by date and store",

      landingOperationsTitle: "Everything that needs your attention in one view.",
      landingOperationsDesc: "The Operations Center aggregates data from all your modules so you know what needs immediate action.",
      landingOperations1: "Active and pending conversations",
      landingOperations2: "Recent orders and their status",
      landingOperations3: "Executed and failed automations",
      landingOperations4: "Connected integration status",
      landingOperations5: "Incomplete configuration alerts",

      landingMultiStoreTitle: "One account. Multiple stores.",
      landingMultiStoreDesc: "Manage multiple stores from a single organization with separate data and centralized control.",
      landingMultiStore1: "Stores with independent configurations",
      landingMultiStore2: "Conversations and orders separated by store",
      landingMultiStore3: "Permissions and roles by store",
      landingMultiStore4: "Commerce and WhatsApp by store",
      landingMultiStore5: "Consolidated or per-store analytics",

      landingIntegrationsTitle: "Integrations that connect your operation.",
      landingIntegrationsSubtitle: "Diaglob connects with the tools you already use.",
      landingIntegrationWhatsapp: "Connect your WhatsApp number to receive and respond to messages.",
      landingIntegrationShopify: "Sync products, variants and manage orders from Diaglob.",
      landingIntegrationDropi: "Dropi integration for shipping and logistics management.",
      landingIntegrationAvailable: "Available",
      landingIntegrationComingSoon: "Coming soon",

      landingTargetTitle: "Built for operations that sell through conversation.",
      landingTargetSubtitle: "Diaglob serves different types of businesses that use WhatsApp as a sales channel.",
      landingTargetEcommerceTitle: "Ecommerce",
      landingTargetEcommerceDesc: "Online stores that sell on WhatsApp and need to organize their operation.",
      landingTargetDropshippingTitle: "Dropshipping",
      landingTargetDropshippingDesc: "Businesses that manage multiple suppliers and sales channels.",
      landingTargetDtcTitle: "DTC Brands",
      landingTargetDtcDesc: "Brands that sell directly to consumers and want to personalize the experience.",
      landingTargetWhatsappTitle: "WhatsApp stores",
      landingTargetWhatsappDesc: "Businesses that already use WhatsApp as their main sales channel.",
      landingTargetMultiStoreTitle: "Multi-store",
      landingTargetMultiStoreDesc: "Operations that manage multiple stores and need a centralized view.",

      landingBenefitsTitle: "Benefits for your operation.",
      landingBenefit1Title: "Respond faster",
      landingBenefit1Desc: "Centralize conversations so your team responds without losing context.",
      landingBenefit2Title: "Reduce repetitive work",
      landingBenefit2Desc: "Automate tasks that run the same way every time an event occurs.",
      landingBenefit3Title: "Organize orders",
      landingBenefit3Desc: "Manage orders connected to conversations with clear statuses.",
      landingBenefit4Title: "Centralize multiple stores",
      landingBenefit4Desc: "One view for all your stores with separated data.",
      landingBenefit5Title: "Detect issues before",
      landingBenefit5Desc: "The Operations Center shows alerts when something needs attention.",
      landingBenefit6Title: "Measure the operation",
      landingBenefit6Desc: "Analytics with real metrics for conversations, commerce and automations.",

      landingFaqTitle: "Frequently asked questions",
      landingFaqSubtitle: "We answer the most common questions about Diaglob.",
      landingFaqWhatIs: "What is Diaglob?",
      landingFaqWhatIsAnswer: "Diaglob is a platform that centralizes WhatsApp, commerce, automations and analytics so your ecommerce operation runs in an organized way.",
      landingFaqShopify: "Do I need Shopify to use Diaglob?",
      landingFaqShopifyAnswer: "No. Shopify is an optional integration. You can use Diaglob with or without Shopify. The integration lets you sync products and manage orders directly.",
      landingFaqWhatsapp: "Does it work with WhatsApp?",
      landingFaqWhatsappAnswer: "Yes. Diaglob connects directly to your WhatsApp Business number to receive and respond to conversations.",
      landingFaqMultiStore: "Can I manage multiple stores?",
      landingFaqMultiStoreAnswer: "Yes. Diaglob supports multi-store. Each store has its own configuration, conversations and data, all managed from a single organization.",
      landingFaqAi: "What can the AI do?",
      landingFaqAiAnswer: "AI Agents can automatically respond to specific business configurations, recommend products and resolve frequent questions. They are configured with rules and knowledge you define.",
      landingFaqAutomations: "What are automations?",
      landingFaqAutomationsAnswer: "Automations are rules that execute actions when events occur. For example: when an order is created, log follow-up automatically.",
      landingFaqMetrics: "Can I see metrics from my operation?",
      landingFaqMetricsAnswer: "Yes. The Analytics module shows metrics for conversations, messages, orders, average value, automations and top products. You can also filter by date and store.",
      landingFaqDropi: "Is Dropi available yet?",
      landingFaqDropiAnswer: "Dropi is in the process of being integrated. It currently shows as 'Coming soon'. When the official API is available, it will be activated automatically.",
      landingFaqPricing: "How much does it cost?",
      landingFaqPricingAnswer: "Diaglob offers plans from $19 USD/month (Starter) to $179 USD/month (Scale). Each plan includes different amounts of active stores and features.",
      landingFaqChangePlan: "Can I change plans?",
      landingFaqChangePlanAnswer: "Yes. You can change plans at any time. Upgrades apply immediately with proration. Downgrades apply when your current period renews.",
      landingFaqDataSeparation: "Is each store's data separated?",
      landingFaqDataSeparationAnswer: "Yes. Each store has its own conversations, products, orders and configurations. Data is never mixed between stores within the same organization.",

      landingCtaFinalTitle: "Organize today the operation you want to scale tomorrow.",
      landingCtaFinalSubtitle: "Create your free account and start centralizing your operation.",
      landingCtaFinalButton: "Create account",

      landingFooterTagline: "Conversations, commerce and automation for ecommerce.",
      landingFooterProduct: "Product",
      landingFooterLegal: "Legal",
      landingFooterAccount: "Account",
      landingFooterPrivacy: "Privacy",
      landingFooterTerms: "Terms",
      landingFooterRights: "All rights reserved.",

      landingMockOverview: "Overview",
      landingMockConversations: "Conversations",
      landingMockCommerce: "Commerce",
      landingMockAutomations: "Automations",
      landingMockAnalytics: "Analytics",
      landingMockResolved: "Resolved",
      landingMockOrders: "Orders",

      themeSwitchLight: "Switch to light mode",
      themeSwitchDark: "Switch to dark mode",

      landingSolution1: "Centralized conversations",
      landingSolution2: "Connected commerce",
      landingSolution3: "Automations",
      landingSolution4: "Analytics + Operations",

      landingPricingTitle: "Simple, scalable plans",
      landingPricingSubtitle: "Choose the plan that best fits your operation.",
      landingPricingRecommended: "Recommended",
      landingPricingMonth: "USD / month",
      landingPricingStore: "active store",
      landingPricingStores: "active stores",
      landingPricingCta: "Get started",

      landingPlanStarterFeature1: "1 active store",
      landingPlanStarterFeature2: "WhatsApp conversations",
      landingPlanStarterFeature3: "Basic commerce",
      landingPlanStarterFeature4: "Essential analytics",
      landingPlanStarterFeature5: "Email support",
      landingPlanStarterFeature6: "1 AI Agent",

      landingPlanGrowthFeature1: "2 active stores",
      landingPlanGrowthFeature2: "Automations",
      landingPlanGrowthFeature3: "Advanced AI Agents",
      landingPlanGrowthFeature4: "Full analytics",
      landingPlanGrowthFeature5: "Operations Center",
      landingPlanGrowthFeature6: "Priority support",

      landingPlanProFeature1: "3 active stores",
      landingPlanProFeature2: "Everything in Growth",
      landingPlanProFeature3: "Full multi-store",
      landingPlanProFeature4: "Team and permissions",
      landingPlanProFeature5: "Knowledge Bases",
      landingPlanProFeature6: "Dedicated support",

      landingPlanScaleFeature1: "5 active stores",
      landingPlanScaleFeature2: "Everything in Pro",
      landingPlanScaleFeature3: "Maximum capacity",
      landingPlanScaleFeature4: "Advanced integrations",
      landingPlanScaleFeature5: "Guaranteed SLA",
      landingPlanScaleFeature6: "Personalized onboarding",

      landingFooterFeatures: "Features",
      landingFooterIntegrations: "Integrations",
      landingFooterPricing: "Pricing",
      landingFooterLogin: "Sign in",
      landingFooterRegister: "Create account",

      landingBuiltTitle: "Connected knowledge. Multi-country operations.",
      landingBuiltSubtitle: "Bring your business data together with an architecture built for multiple stores and markets.",

      landingKnowledgeLabel: "KNOWLEDGE BASE",
      landingKnowledgeDesc: "Centralized, contextual information for your agents.",
      landingKnowledgeHighlight: "Your AI is only as good as the knowledge it has.",

      landingSourceGoogleSheets: "Google Sheets",
      landingSourceGoogleSheetsStatus: "Available",
      landingSourceGoogleSheetsDesc: "Connect information that changes constantly.",
      landingSourceExcel: "Excel / CSV",
      landingSourceExcelStatus: "Available",
      landingSourceExcelDesc: "Upload files with products, policies or business information.",
      landingSourceShopify: "Shopify",
      landingSourceShopifyStatus: "Available",
      landingSourceShopifyDesc: "Connect your store product data with your Diaglob operation.",
      landingSourceDropi: "Dropi",
      landingSourceDropiStatus: "Coming soon",
      landingSourceDropiDesc: "Dropi catalog and operation integration in preparation.",

      landingAgentLabel: "AI AGENT",
      landingAgentDesc: "Responds using real context from your business.",

      landingResultRespond: "Respond",
      landingResultRespondDesc: "More relevant answers with context.",
      landingResultRecommend: "Recommend",
      landingResultRecommendDesc: "Products with real context.",
      landingResultAutomate: "Automate",
      landingResultAutomateDesc: "Actions based on business information.",

      landingBuiltMultiTitle: "Multiple stores. Multiple markets. One operation.",
      landingBuiltMultiSubtitle: "Manage different stores, markets, currencies, languages and integrations from a single platform.",

      landingStoreColombia: "Colombia",
      landingStoreMexico: "Mexico",
      landingStoreUsa: "USA",
      landingStoreCurrencyCOP: "COP",
      landingStoreCurrencyMXN: "MXN",
      landingStoreCurrencyUSD: "USD",
      landingStoreLangEs: "ES",
      landingStoreLangEn: "EN",

      landingOpsCenter: "Operations Center",
      landingOpsCenterDesc: "Analytics, automations and team centralized.",

      landingBuiltEachStore: "Each store operates with its own context, settings and integrations while you keep centralized visibility.",
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
