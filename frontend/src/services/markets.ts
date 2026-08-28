import { api } from "./api";


export interface Market {
  country_code: string;
  country_name: string;
  country_name_en: string;
  region:
    | "north_america"
    | "central_america"
    | "caribbean"
    | "south_america";

  currency: string;

  supported_currencies?: string[];

  default_language: string;
  languages: string[];

  default_timezone: string;
}


export interface MarketsResponse {
  items: Market[];
  total: number;
}


export async function getMarkets() {
  const response =
    await api.get<MarketsResponse>(
      "/api/markets",
      {
        headers: {
          "X-Diaglob-Global-Scope": "1",
        },
      },
    );

  return response.data;
}


export async function getMarket(
  countryCode: string,
) {
  const response =
    await api.get<Market>(
      `/api/markets/${countryCode}`,
      {
        headers: {
          "X-Diaglob-Global-Scope": "1",
        },
      },
    );

  return response.data;
}
