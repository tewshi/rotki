import type { AsyncComponent } from 'vue';

export const SOURCES = [
  'cointracking',
  'cryptocom',
  'icon',
  'zip',
  'csv',
  'json',
  'nexo',
  'blockfi_transactions',
  'blockfi_trades',
  'shapeshift_trades',
  'uphold_transactions',
  'bisq_trades',
  'binance',
  'bitcoin_tax',
  'bitmex_wallet_history',
  'bitstamp',
  'rotki_events',
  'rotki_trades',
  'bittrex',
  'kucoin',
] as const;

export type ImportSourceType = (typeof SOURCES)[number];

export interface ImportSource {
  identifier: string;
  name: string;
  logo?: string;
  icon?: string;
  form: AsyncComponent;
}
