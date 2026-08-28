const COUNTRY_NAMES_ES =
  new Intl.DisplayNames(
    ["es"],
    {
      type: "region",
    },
  );


const CURRENCY_LOCALES: Record<
  string,
  string
> = {
  ARS: "es-AR",
  BBD: "en-BB",
  BOB: "es-BO",
  BRL: "pt-BR",
  BSD: "en-BS",
  BZD: "en-BZ",
  CAD: "en-CA",
  CLP: "es-CL",
  COP: "es-CO",
  CRC: "es-CR",
  CUP: "es-CU",
  DOP: "es-DO",
  GTQ: "es-GT",
  GYD: "en-GY",
  HNL: "es-HN",
  HTG: "fr-HT",
  JMD: "en-JM",
  MXN: "es-MX",
  NIO: "es-NI",
  PAB: "es-PA",
  PEN: "es-PE",
  PYG: "es-PY",
  SRD: "nl-SR",
  TTD: "en-TT",
  USD: "en-US",
  UYU: "es-UY",
  VES: "es-VE",
  XCD: "en-AG",
};


const ZERO_DECIMAL_CURRENCIES =
  new Set([
    "CLP",
    "COP",
    "PYG",
  ]);


export function getCountryName(
  countryCode: string,
) {
  const code =
    countryCode
      .trim()
      .toUpperCase();

  if (!/^[A-Z]{2}$/.test(code)) {
    return code;
  }

  return (
    COUNTRY_NAMES_ES.of(code)
    || code
  );
}


export function getCountryFlag(
  countryCode: string,
) {
  const code =
    countryCode
      .trim()
      .toUpperCase();

  if (!/^[A-Z]{2}$/.test(code)) {
    return "🌍";
  }

  return String.fromCodePoint(
    ...[...code].map(
      (character) =>
        127397 +
        character.charCodeAt(0),
    ),
  );
}


export function getCurrencyLocale(
  currency: string,
  countryCode?: string,
) {
  if (
    countryCode &&
    /^[A-Z]{2}$/i.test(
      countryCode
    )
  ) {
    const language =
      getDefaultLocaleLanguage(
        countryCode
      );

    return (
      `${language}-${countryCode.toUpperCase()}`
    );
  }

  return (
    CURRENCY_LOCALES[
      currency.toUpperCase()
    ]
    || "en-US"
  );
}


function getDefaultLocaleLanguage(
  countryCode: string,
) {
  switch (
    countryCode
      .trim()
      .toUpperCase()
  ) {
    case "BR":
      return "pt";

    case "CA":
      return "en";

    case "US":
    case "BZ":
    case "AG":
    case "BS":
    case "BB":
    case "DM":
    case "GD":
    case "JM":
    case "KN":
    case "LC":
    case "VC":
    case "TT":
    case "GY":
      return "en";

    case "HT":
      return "fr";

    case "SR":
      return "nl";

    default:
      return "es";
  }
}


export function formatMoney(
  amount: number,
  currency: string,
  countryCode?: string,
) {
  const normalizedCurrency =
    currency.toUpperCase();

  const locale =
    getCurrencyLocale(
      normalizedCurrency,
      countryCode,
    );

  const fractionDigits =
    ZERO_DECIMAL_CURRENCIES.has(
      normalizedCurrency
    )
      ? 0
      : 2;

  const formatted =
    new Intl.NumberFormat(
      locale,
      {
        style: "currency",
        currency:
          normalizedCurrency,

        minimumFractionDigits:
          fractionDigits,

        maximumFractionDigits:
          fractionDigits,
      },
    ).format(amount);

  return (
    `${formatted} `
    + normalizedCurrency
  );
}


export function getLanguageName(
  language: string,
) {
  switch (
    language
      .toLowerCase()
      .split("-")[0]
  ) {
    case "es":
      return "Español";

    case "en":
      return "English";

    case "pt":
      return "Português";

    case "fr":
      return "Français";

    case "ht":
      return "Kreyòl ayisyen";

    case "nl":
      return "Nederlands";

    case "gn":
      return "Guaraní";

    default:
      return language.toUpperCase();
  }
}
