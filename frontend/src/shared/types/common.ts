export type ShopId = 1 | 2;
export type ShopSelection = 0 | ShopId;
export type Channel = "FBP" | "realFBS" | "WHD";

export interface Shop {
  id: ShopId;
  name: string;
}

export interface OkResponse {
  ok: boolean;
}
