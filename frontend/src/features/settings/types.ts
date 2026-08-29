export interface OzonProbeCompany {
  name?: string | number | null;
  inn?: string | number | null;
}

export interface OzonProbeIdentity {
  company?: OzonProbeCompany | null;
  name?: string | number | null;
  seller_id?: string | number | null;
  client_id?: string | number | null;
  inn?: string | number | null;
  ogrn?: string | number | null;
}

export interface OzonProbePermissions {
  orders?: string;
  returns?: string;
  stock?: string;
}

export interface OzonProbeResponse {
  valid: boolean;
  identity?: OzonProbeIdentity;
  roles?: string[];
  permissions?: OzonProbePermissions;
  error?: string;
}

export type OzonProbeStatus = "idle" | "loading" | "success" | "error";
