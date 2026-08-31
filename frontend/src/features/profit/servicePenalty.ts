import { request } from "../../shared/api/client";

export interface ServicePenaltyRate {
  service_penalty_exchange_rate: string;
  valid_from_utc: string;
  valid_to_utc: string;
}

export interface CurrentServicePenaltyExchangeRates {
  source: string;
  as_of: string;
  rates: {
    USD: ServicePenaltyRate | null;
    CNY: ServicePenaltyRate | null;
  };
  error?: string;
}

export function getCurrentServicePenaltyExchangeRates(): Promise<CurrentServicePenaltyExchangeRates> {
  return request<CurrentServicePenaltyExchangeRates>("/api/exchange-rates/current-service-penalty");
}
