import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowUpRight,
  Bot,
  BrainCircuit,
  CornerDownLeft,
  LoaderCircle,
  MessageSquareText,
  Package,
  Search,
  ShoppingBag,
  Store as StoreIcon,
  Users,
  Workflow,
  X,
} from "lucide-react";

import {
  searchWorkspace,
  type GlobalSearchCategories,
  type GlobalSearchResult,
  type GlobalSearchResultKind,
} from "../services/globalSearch";
import { normalizeGlobalSearchQuery } from "../services/globalSearchHelpers";
import type { Store } from "../services/stores";
import "../global-search.css";


interface SearchNavigationItem {
  key: string;
  label: string;
}


interface GlobalSearchPaletteProps {
  navigation: SearchNavigationItem[];
  stores: Store[];
  selectedStoreId: string;
  locale: "es" | "en" | "pt-BR";
  onSelect: (result: GlobalSearchResult) => void;
  onChangeStore: (storeId: string) => void;
}


const COPY = {
  es: {
    trigger: "Buscar en Diaglob",
    input: "Buscar clientes, pedidos, productos, conversaciones...",
    hint: "Escribe al menos 2 caracteres para buscar datos de la tienda.",
    navigation: "Navegación",
    results: "Resultados",
    recent: "Accesos rápidos",
    empty: "No encontramos resultados para esta búsqueda.",
    loading: "Buscando...",
    clear: "Limpiar búsqueda",
    activeStore: "Tienda activa",
    switchStore: "Cambiar a esta tienda",
    keyboard: "↑↓ navegar · Enter abrir · Esc cerrar",
  },
  en: {
    trigger: "Search Diaglob",
    input: "Search customers, orders, products, conversations...",
    hint: "Type at least 2 characters to search store data.",
    navigation: "Navigation",
    results: "Results",
    recent: "Quick access",
    empty: "No results found for this search.",
    loading: "Searching...",
    clear: "Clear search",
    activeStore: "Active store",
    switchStore: "Switch to this store",
    keyboard: "↑↓ navigate · Enter open · Esc close",
  },
  "pt-BR": {
    trigger: "Buscar no Diaglob",
    input: "Buscar clientes, pedidos, produtos, conversas...",
    hint: "Digite pelo menos 2 caracteres para buscar dados da loja.",
    navigation: "Navegação",
    results: "Resultados",
    recent: "Acessos rápidos",
    empty: "Nenhum resultado encontrado para esta busca.",
    loading: "Buscando...",
    clear: "Limpar busca",
    activeStore: "Loja ativa",
    switchStore: "Mudar para esta loja",
    keyboard: "↑↓ navegar · Enter abrir · Esc fechar",
  },
} as const;


const KIND_LABELS: Record<
  "es" | "en" | "pt-BR",
  Record<GlobalSearchResultKind, string>
> = {
  es: {
    navigation: "Sección",
    conversation: "Conversación",
    customer: "Cliente",
    product: "Producto",
    order: "Pedido",
    automation: "Automatización",
    agent: "Agente IA",
    knowledge: "Knowledge Base",
    store: "Tienda",
  },
  en: {
    navigation: "Section",
    conversation: "Conversation",
    customer: "Customer",
    product: "Product",
    order: "Order",
    automation: "Automation",
    agent: "AI agent",
    knowledge: "Knowledge Base",
    store: "Store",
  },
  "pt-BR": {
    navigation: "Seção",
    conversation: "Conversa",
    customer: "Cliente",
    product: "Produto",
    order: "Pedido",
    automation: "Automação",
    agent: "Agente IA",
    knowledge: "Knowledge Base",
    store: "Loja",
  },
};


const ICONS: Record<GlobalSearchResultKind, typeof Search> = {
  navigation: ArrowUpRight,
  conversation: MessageSquareText,
  customer: Users,
  product: Package,
  order: ShoppingBag,
  automation: Workflow,
  agent: Bot,
  knowledge: BrainCircuit,
  store: StoreIcon,
};


function buildLocalResults(
  query: string,
  navigation: SearchNavigationItem[],
  stores: Store[],
): GlobalSearchResult[] {
  const normalized = normalizeGlobalSearchQuery(query);
  if (!normalized) return [];

  const navigationResults = navigation
    .filter((item) =>
      normalizeGlobalSearchQuery(item.label).includes(normalized),
    )
    .slice(0, 6)
    .map((item) => ({
      key: `navigation:${item.key}`,
      kind: "navigation" as const,
      title: item.label,
      subtitle: "",
      page: item.key,
      query: item.label,
    }));

  const storeResults = stores
    .filter((store) => store.active)
    .filter((store) => {
      const haystack = [
        store.name,
        store.slug,
        store.country_code,
        store.currency,
        store.shopify_domain || "",
      ]
        .map(normalizeGlobalSearchQuery)
        .join(" ");
      return haystack.includes(normalized);
    })
    .slice(0, 4)
    .map((store) => ({
      key: `store:${store.id}`,
      kind: "store" as const,
      title: store.name,
      subtitle: [store.country_code, store.currency].filter(Boolean).join(" · "),
      page: "overview",
      storeId: store.id,
      query: store.name,
    }));

  return [...navigationResults, ...storeResults];
}


export default function GlobalSearchPalette({
  navigation,
  stores,
  selectedStoreId,
  locale,
  onSelect,
  onChangeStore,
}: GlobalSearchPaletteProps) {
  const copy = COPY[locale];
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [remoteResults, setRemoteResults] = useState<GlobalSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const requestRef = useRef(0);

  const pageKeys = useMemo(
    () => new Set(navigation.map((item) => item.key)),
    [navigation],
  );

  const categories = useMemo<GlobalSearchCategories>(
    () => ({
      conversations: pageKeys.has("conversations"),
      customers: pageKeys.has("customers"),
      commerce: pageKeys.has("commerce"),
      automations: pageKeys.has("automations"),
      agents: pageKeys.has("agents"),
      knowledge: pageKeys.has("knowledge"),
    }),
    [pageKeys],
  );

  const localResults = useMemo(
    () => buildLocalResults(query, navigation, stores),
    [query, navigation, stores],
  );

  const results = useMemo(() => {
    const seen = new Set<string>();
    return [...localResults, ...remoteResults].filter((result) => {
      if (seen.has(result.key)) return false;
      seen.add(result.key);
      return true;
    });
  }, [localResults, remoteResults]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
      }

      if (event.key === "Escape" && open) {
        event.preventDefault();
        setOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => inputRef.current?.focus());

    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
    const normalized = normalizeGlobalSearchQuery(query);

    if (!open || normalized.length < 2) {
      requestRef.current += 1;
      setRemoteResults([]);
      setLoading(false);
      return;
    }

    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    setLoading(true);

    const timer = window.setTimeout(() => {
      void searchWorkspace({
        query,
        storeId: Number(selectedStoreId) || undefined,
        categories,
      }).then((nextResults) => {
        if (requestRef.current !== requestId) return;
        setRemoteResults(nextResults);
        setLoading(false);
      });
    }, 250);

    return () => window.clearTimeout(timer);
  }, [query, open, selectedStoreId, categories]);

  function close() {
    setOpen(false);
    setQuery("");
    setRemoteResults([]);
    setActiveIndex(0);
  }

  function selectResult(result: GlobalSearchResult) {
    if (result.kind === "store" && result.storeId) {
      onChangeStore(String(result.storeId));
      close();
      return;
    }

    onSelect(result);
    close();
  }

  function handleInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) =>
        results.length === 0 ? 0 : (current + 1) % results.length,
      );
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) =>
        results.length === 0
          ? 0
          : (current - 1 + results.length) % results.length,
      );
      return;
    }

    if (event.key === "Enter" && results[activeIndex]) {
      event.preventDefault();
      selectResult(results[activeIndex]);
    }
  }

  const normalized = normalizeGlobalSearchQuery(query);

  return (
    <>
      <button
        type="button"
        className="dg-search-trigger"
        aria-label={copy.trigger}
        onClick={() => setOpen(true)}
      >
        <Search size={16} />
        <span>{copy.trigger}</span>
        <kbd>⌘ K</kbd>
      </button>

      {open && (
        <div
          className="dg-global-search-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) close();
          }}
        >
          <section
            className="dg-global-search"
            role="dialog"
            aria-modal="true"
            aria-label={copy.trigger}
          >
            <div className="dg-global-search-input-row">
              <Search size={19} />
              <input
                ref={inputRef}
                type="search"
                value={query}
                placeholder={copy.input}
                aria-label={copy.trigger}
                autoComplete="off"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={handleInputKeyDown}
              />
              {loading && <LoaderCircle className="spin" size={18} />}
              {query && !loading && (
                <button
                  type="button"
                  className="dg-global-search-clear"
                  onClick={() => setQuery("")}
                  aria-label={copy.clear}
                >
                  <X size={17} />
                </button>
              )}
              <kbd>ESC</kbd>
            </div>

            <div className="dg-global-search-body">
              {!normalized && (
                <div className="dg-global-search-quick">
                  <span className="dg-global-search-section-label">{copy.recent}</span>
                  {navigation.slice(0, 6).map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      className="dg-global-search-quick-item"
                      onClick={() => selectResult({
                        key: `navigation:${item.key}`,
                        kind: "navigation",
                        title: item.label,
                        subtitle: "",
                        page: item.key,
                      })}
                    >
                      <ArrowUpRight size={15} />
                      <span>{item.label}</span>
                    </button>
                  ))}
                </div>
              )}

              {normalized.length === 1 && (
                <div className="dg-global-search-hint">{copy.hint}</div>
              )}

              {normalized && results.length > 0 && (
                <div className="dg-global-search-results">
                  <span className="dg-global-search-section-label">
                    {localResults.length > 0 && remoteResults.length === 0
                      ? copy.navigation
                      : copy.results}
                  </span>

                  {results.map((result, index) => {
                    const Icon = ICONS[result.kind];
                    const isSelected = index === activeIndex;
                    const isCurrentStore =
                      result.kind === "store"
                      && String(result.storeId) === selectedStoreId;

                    return (
                      <button
                        key={result.key}
                        type="button"
                        className={`dg-global-search-result ${isSelected ? "is-selected" : ""}`}
                        onMouseEnter={() => setActiveIndex(index)}
                        onClick={() => selectResult(result)}
                      >
                        <span className={`dg-global-search-result-icon kind-${result.kind}`}>
                          <Icon size={17} />
                        </span>
                        <span className="dg-global-search-result-copy">
                          <strong>{result.title}</strong>
                          <small>
                            <span>{KIND_LABELS[locale][result.kind]}</span>
                            {result.subtitle && <span> · {result.subtitle}</span>}
                            {isCurrentStore && <span> · {copy.activeStore}</span>}
                          </small>
                        </span>
                        <span className="dg-global-search-open-hint">
                          {result.kind === "store" && !isCurrentStore
                            ? copy.switchStore
                            : <CornerDownLeft size={14} />}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}

              {normalized.length >= 2 && !loading && results.length === 0 && (
                <div className="dg-global-search-empty">
                  <Search size={24} />
                  <p>{copy.empty}</p>
                </div>
              )}

              {loading && results.length === 0 && (
                <div className="dg-global-search-empty">
                  <LoaderCircle className="spin" size={24} />
                  <p>{copy.loading}</p>
                </div>
              )}
            </div>

            <footer className="dg-global-search-footer">
              <span>{copy.keyboard}</span>
              <span>{selectedStoreId ? `${copy.activeStore}: ${stores.find((store) => String(store.id) === selectedStoreId)?.name || "—"}` : ""}</span>
            </footer>
          </section>
        </div>
      )}
    </>
  );
}
