export type ProductRuleMemberType = "sku" | "offer_id";
export type ProductRuleWriteKind = "short_name" | "delete_short_name" | "merge" | "dissolve";

export interface ProductRulesSummary {
  short_names: number;
  merges: number;
}

export interface ProductShortName {
  sku: string;
  short_name: string;
  updated_at: string;
}

export interface ProductRuleMember {
  key_type: ProductRuleMemberType;
  key_value: string;
}

export interface ProductRuleGroup {
  id: number;
  primary_offer_id: string | null;
  primary_sku: string | null;
  status: string;
  note: string;
  updated_at: string;
  product_name: string;
  members: ProductRuleMember[];
}

export interface ProductRuleConflict {
  key_type: "merge";
  key_value: string;
  note: string;
}

export interface ProductRuleProduct {
  sku: string;
  offer_id: string;
  product_name: string;
}

export interface ProductRulesResponse {
  summary: ProductRulesSummary;
  short_names: ProductShortName[];
  groups: ProductRuleGroup[];
  products: ProductRuleProduct[];
  conflicts: ProductRuleConflict[];
  fixed_rule: string;
}

export interface ProductRuleShortNamePayload {
  kind: "short_name";
  sku: string;
  short_name: string;
}

export interface ProductRuleDeleteShortNamePayload {
  kind: "delete_short_name";
  sku: string;
}

export interface ProductRuleMergePayload {
  kind: "merge";
  id: number;
  primary_offer_id: string;
  primary_sku: string;
  members: ProductRuleMember[];
}

export interface ProductRuleDissolvePayload {
  kind: "dissolve";
  id: number;
}
