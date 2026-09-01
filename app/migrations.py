import json

from .db import DEFAULT_ALERT_RULE_CONFIGS, transaction

SCHEMA_VERSION = 13


def _create_webhook_events(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS ozon_webhook_events (
      event_key TEXT NOT NULL, shop_id INTEGER NOT NULL REFERENCES shops(id),
      message_type TEXT NOT NULL, posting_number TEXT, order_number TEXT,
      occurred_at TEXT, payload_json TEXT NOT NULL, received_at TEXT NOT NULL,
      applied_at TEXT, error TEXT, PRIMARY KEY(shop_id,event_key));
    CREATE INDEX IF NOT EXISTS idx_ozon_webhook_events_posting
      ON ozon_webhook_events(shop_id,posting_number,occurred_at);
    CREATE INDEX IF NOT EXISTS idx_ozon_webhook_events_pending
      ON ozon_webhook_events(shop_id,applied_at,occurred_at);
    """)


def _create_ad_campaigns(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS ad_campaigns (
      shop_id INTEGER NOT NULL REFERENCES shops(id), campaign_id TEXT NOT NULL,
      name TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '',
      payment_type TEXT, adv_object_type TEXT, placement TEXT,
      weekly_budget REAL, created_at TEXT, updated_at TEXT,
      synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
      PRIMARY KEY(shop_id,campaign_id));
    """)


def _create_ad_statistics(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS ad_campaign_daily (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      shop_id INTEGER NOT NULL REFERENCES shops(id), stat_date TEXT NOT NULL,
      campaign_id TEXT NOT NULL, impressions INTEGER, clicks INTEGER, cart_adds INTEGER,
      spend_rub REAL, orders INTEGER, revenue_rub REAL,
      synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
      UNIQUE(shop_id,stat_date,campaign_id));
    CREATE INDEX IF NOT EXISTS idx_ad_campaign_daily_date
      ON ad_campaign_daily(shop_id,stat_date);
    CREATE INDEX IF NOT EXISTS idx_ad_campaign_daily_campaign
      ON ad_campaign_daily(shop_id,campaign_id,stat_date);
    CREATE TABLE IF NOT EXISTS ad_sku_daily (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      shop_id INTEGER NOT NULL REFERENCES shops(id), stat_date TEXT NOT NULL,
      campaign_id TEXT NOT NULL, sku TEXT NOT NULL, product_name TEXT,
      impressions INTEGER, clicks INTEGER, cart_adds INTEGER,
      spend_rub REAL, orders INTEGER, revenue_rub REAL,
      synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
      UNIQUE(shop_id,stat_date,campaign_id,sku));
    CREATE INDEX IF NOT EXISTS idx_ad_sku_daily_date
      ON ad_sku_daily(shop_id,stat_date);
    CREATE INDEX IF NOT EXISTS idx_ad_sku_daily_sku
      ON ad_sku_daily(shop_id,sku,stat_date);
    CREATE INDEX IF NOT EXISTS idx_ad_sku_daily_campaign
      ON ad_sku_daily(shop_id,campaign_id,stat_date);
    """)


def _create_alert_tables(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS alert_rules (
      shop_id INTEGER NOT NULL REFERENCES shops(id), rule_key TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
      notify_dingtalk INTEGER NOT NULL DEFAULT 1 CHECK(notify_dingtalk IN (0,1)),
      config_json TEXT NOT NULL DEFAULT '{}',
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
      PRIMARY KEY(shop_id,rule_key));
    CREATE TABLE IF NOT EXISTS alert_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      shop_id INTEGER NOT NULL REFERENCES shops(id), rule_key TEXT NOT NULL,
      entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
      severity TEXT NOT NULL CHECK(severity IN ('critical','high','warning')),
      title TEXT NOT NULL, message TEXT NOT NULL, metric_json TEXT NOT NULL DEFAULT '{}',
      first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, resolved_at TEXT,
      acknowledged_at TEXT, last_notified_at TEXT, last_notify_error TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_events_open
      ON alert_events(shop_id,rule_key,entity_type,entity_id) WHERE resolved_at IS NULL;
    CREATE INDEX IF NOT EXISTS idx_alert_events_status
      ON alert_events(shop_id,resolved_at,last_seen_at);
    CREATE INDEX IF NOT EXISTS idx_alert_events_severity
      ON alert_events(shop_id,severity,resolved_at,last_seen_at);
    CREATE INDEX IF NOT EXISTS idx_alert_events_rule
      ON alert_events(shop_id,rule_key,resolved_at);
    """)
    rows = [(shop_id, rule_key, json.dumps(config, ensure_ascii=False))
            for shop_id in (1, 2) for rule_key, config in DEFAULT_ALERT_RULE_CONFIGS.items()]
    db.executemany("""INSERT OR IGNORE INTO alert_rules(shop_id,rule_key,config_json)
      VALUES(?,?,?)""", rows)


def _migrate_auto_sync_settings(db):
    if db.execute("SELECT 1 FROM shop_auto_sync_settings WHERE module='ad_campaign_daily' LIMIT 1").fetchone():
        return
    db.execute("ALTER TABLE shop_auto_sync_settings RENAME TO shop_auto_sync_settings_v4")
    db.execute("""CREATE TABLE shop_auto_sync_settings (
      shop_id INTEGER NOT NULL REFERENCES shops(id),
      module TEXT NOT NULL CHECK(module IN ('orders','returns','stock','ad_campaign_daily','ad_sku_daily')),
      enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
      interval_hours INTEGER NOT NULL DEFAULT 24 CHECK(interval_hours IN (1,2,3,4,6,8,12,24)),
      range_days INTEGER NOT NULL CHECK(range_days BETWEEN 1 AND 365), PRIMARY KEY(shop_id,module))""")
    db.execute("""INSERT INTO shop_auto_sync_settings(shop_id,module,enabled,interval_hours,range_days)
      SELECT shop_id,module,enabled,interval_hours,range_days FROM shop_auto_sync_settings_v4""")
    db.execute("""INSERT INTO shop_auto_sync_settings(shop_id,module,enabled,interval_hours,range_days)
      VALUES(1,'ad_campaign_daily',0,24,7),(1,'ad_sku_daily',0,24,7),
            (2,'ad_campaign_daily',0,24,7),(2,'ad_sku_daily',0,24,7)""")
    db.execute("DROP TABLE shop_auto_sync_settings_v4")


def _migrate_v1_to_v2(db):
    _create_webhook_events(db)
    db.execute("PRAGMA user_version=2")


def _migrate_v2_to_v3(db):
    _create_ad_campaigns(db)
    db.execute("PRAGMA user_version=3")


def _migrate_v3_to_v4(db):
    _create_ad_statistics(db)
    db.execute("PRAGMA user_version=4")


def _migrate_v4_to_v5(db):
    _migrate_auto_sync_settings(db)
    db.execute("PRAGMA user_version=5")


def _migrate_v5_to_v6(db):
    _create_alert_tables(db)
    db.execute("PRAGMA user_version=6")


def _migrate_v6_to_v7(db):
    db.execute("""UPDATE sync_runs SET status='failed',
      error=COALESCE(error,'数据库升级时检测到重复运行任务，任务已中断，请重新拉取'),
      finished_at=COALESCE(finished_at,strftime('%Y-%m-%dT%H:%M:%SZ','now'))
      WHERE status='running' AND id NOT IN (
        SELECT MAX(id) FROM sync_runs WHERE status='running' GROUP BY shop_id,module)""")
    db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_one_running ON sync_runs(shop_id,module)
      WHERE status='running'""")
    db.execute("PRAGMA user_version=7")


def _create_product_forecast_costs(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS product_forecast_costs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_identity TEXT NOT NULL UNIQUE,
      purchase_cost REAL NOT NULL,
      purchase_currency TEXT NOT NULL CHECK(purchase_currency IN ('USD','CNY')),
      weight_grams REAL,
      length_cm REAL,
      width_cm REAL,
      height_cm REAL,
      packing_cost_cny REAL,
      other_cost_cny REAL,
      note TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS product_forecast_cost_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      product_identity TEXT NOT NULL,
      purchase_cost REAL NOT NULL,
      purchase_currency TEXT NOT NULL CHECK(purchase_currency IN ('USD','CNY')),
      weight_grams REAL,
      length_cm REAL,
      width_cm REAL,
      height_cm REAL,
      packing_cost_cny REAL,
      other_cost_cny REAL,
      note TEXT NOT NULL DEFAULT '',
      change_note TEXT NOT NULL DEFAULT '',
      recorded_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_product_forecast_cost_history_identity_time
      ON product_forecast_cost_history(product_identity,recorded_at DESC,id DESC);
    """)


def _migrate_v7_to_v8(db):
    _create_product_forecast_costs(db)
    db.execute("PRAGMA user_version=8")


def _migrate_v8_to_v9(db):
    db.execute("ALTER TABLE exchange_rates RENAME COLUMN base_rate TO service_penalty_exchange_rate")
    db.execute("ALTER TABLE exchange_rates RENAME COLUMN rate_with_adjustment TO sales_exchange_rate")
    db.execute("PRAGMA user_version=9")


def _migrate_v9_to_v10(db):
    db.execute("""CREATE TABLE exchange_rates_v10 (
      from_currency TEXT NOT NULL CHECK(from_currency IN ('USD','CNY')),
      to_currency TEXT NOT NULL CHECK(to_currency='RUB'), valid_from_utc TEXT NOT NULL,
      valid_to_utc TEXT NOT NULL, service_penalty_exchange_rate TEXT NOT NULL,
      sales_exchange_rate TEXT,
      source TEXT NOT NULL DEFAULT 'ozon_xapi' CHECK(source='ozon_xapi'), fetched_at TEXT NOT NULL,
      PRIMARY KEY(from_currency,to_currency,valid_from_utc,valid_to_utc));""")
    db.execute("""INSERT INTO exchange_rates_v10(
      from_currency,to_currency,valid_from_utc,valid_to_utc,
      service_penalty_exchange_rate,sales_exchange_rate,source,fetched_at)
      SELECT from_currency,to_currency,valid_from_utc,valid_to_utc,
        service_penalty_exchange_rate,sales_exchange_rate,source,fetched_at
      FROM exchange_rates""")
    db.execute("DROP TABLE exchange_rates")
    db.execute("ALTER TABLE exchange_rates_v10 RENAME TO exchange_rates")
    db.execute("PRAGMA user_version=10")


def _create_finance_tables(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS ozon_finance_transactions (
      shop_id INTEGER NOT NULL REFERENCES shops(id), operation_id TEXT NOT NULL,
      operation_type TEXT NOT NULL, operation_type_name TEXT NOT NULL DEFAULT '',
      transaction_type TEXT NOT NULL DEFAULT '', operation_date TEXT NOT NULL,
      posting_number TEXT, order_date TEXT, delivery_schema TEXT NOT NULL DEFAULT '',
      warehouse_id TEXT, amount REAL NOT NULL, accruals_for_sale REAL NOT NULL,
      sale_commission REAL NOT NULL, delivery_charge REAL NOT NULL,
      return_delivery_charge REAL NOT NULL,
      currency TEXT NOT NULL CHECK(currency IN ('USD','CNY')),
      payload_json TEXT NOT NULL, fetched_at TEXT NOT NULL,
      PRIMARY KEY(shop_id,operation_id));
    CREATE INDEX IF NOT EXISTS idx_finance_transactions_date
      ON ozon_finance_transactions(shop_id,operation_date);
    CREATE INDEX IF NOT EXISTS idx_finance_transactions_posting_date
      ON ozon_finance_transactions(shop_id,posting_number,operation_date);
    CREATE INDEX IF NOT EXISTS idx_finance_transactions_operation_type_date
      ON ozon_finance_transactions(shop_id,operation_type,operation_date);
    CREATE INDEX IF NOT EXISTS idx_finance_transactions_transaction_type_date
      ON ozon_finance_transactions(shop_id,transaction_type,operation_date);

    CREATE TABLE IF NOT EXISTS ozon_finance_transaction_items (
      shop_id INTEGER NOT NULL, operation_id TEXT NOT NULL, line_no INTEGER NOT NULL,
      sku TEXT, name TEXT NOT NULL DEFAULT '',
      PRIMARY KEY(shop_id,operation_id,line_no),
      FOREIGN KEY(shop_id,operation_id)
        REFERENCES ozon_finance_transactions(shop_id,operation_id) ON DELETE CASCADE);

    CREATE TABLE IF NOT EXISTS ozon_finance_transaction_services (
      shop_id INTEGER NOT NULL, operation_id TEXT NOT NULL, line_no INTEGER NOT NULL,
      service_name TEXT NOT NULL DEFAULT '', price REAL NOT NULL,
      PRIMARY KEY(shop_id,operation_id,line_no),
      FOREIGN KEY(shop_id,operation_id)
        REFERENCES ozon_finance_transactions(shop_id,operation_id) ON DELETE CASCADE);

    CREATE TABLE IF NOT EXISTS ozon_finance_reconciliations (
      shop_id INTEGER NOT NULL REFERENCES shops(id), period_from TEXT NOT NULL,
      period_to TEXT NOT NULL, api_row_count INTEGER NOT NULL,
      fetched_operation_count INTEGER NOT NULL, accruals_for_sale REAL NOT NULL,
      sale_commission REAL NOT NULL, processing_and_delivery REAL NOT NULL,
      refunds_and_cancellations REAL NOT NULL, services_amount REAL NOT NULL,
      compensation_amount REAL NOT NULL, money_transfer REAL NOT NULL,
      others_amount REAL NOT NULL, local_amount_total REAL NOT NULL,
      remote_component_total REAL NOT NULL, difference REAL NOT NULL,
      reconciliation_status TEXT NOT NULL CHECK(reconciliation_status IN ('matched','mismatch')),
      fetched_at TEXT NOT NULL, PRIMARY KEY(shop_id,period_from,period_to));
    """)


def _create_erp_cost_tables(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS erp_cost_import_batches (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      shop_id INTEGER NOT NULL REFERENCES shops(id), filename TEXT NOT NULL,
      row_count INTEGER NOT NULL, parsed_count INTEGER NOT NULL,
      inserted_count INTEGER NOT NULL, updated_count INTEGER NOT NULL,
      unchanged_count INTEGER NOT NULL, imported_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS erp_order_item_costs (
      shop_id INTEGER NOT NULL REFERENCES shops(id),
      erp_order_number TEXT NOT NULL, ozon_sku TEXT NOT NULL, offer_id TEXT,
      quantity INTEGER NOT NULL CHECK(quantity>0), unit_cost TEXT NOT NULL,
      exchange_rate_original TEXT, total_cost TEXT NOT NULL,
      platform_link TEXT NOT NULL DEFAULT '', source_batch_id INTEGER NOT NULL
        REFERENCES erp_cost_import_batches(id), source_row_no INTEGER NOT NULL,
      raw_payload_json TEXT NOT NULL, imported_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      PRIMARY KEY(shop_id,erp_order_number,ozon_sku));
    CREATE INDEX IF NOT EXISTS idx_erp_order_item_costs_order
      ON erp_order_item_costs(shop_id,erp_order_number);
    CREATE INDEX IF NOT EXISTS idx_erp_order_item_costs_sku
      ON erp_order_item_costs(shop_id,ozon_sku);
    CREATE INDEX IF NOT EXISTS idx_erp_order_item_costs_offer
      ON erp_order_item_costs(shop_id,offer_id);
    """)


def _migrate_v10_to_v11(db):
    db.execute("ALTER TABLE shop_auto_sync_settings RENAME TO shop_auto_sync_settings_v10")
    db.execute("""CREATE TABLE shop_auto_sync_settings (
      shop_id INTEGER NOT NULL REFERENCES shops(id),
      module TEXT NOT NULL CHECK(module IN (
        'orders','returns','stock','ad_campaign_daily','ad_sku_daily','finance_transactions')),
      enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
      interval_hours INTEGER NOT NULL DEFAULT 24 CHECK(interval_hours IN (1,2,3,4,6,8,12,24)),
      range_days INTEGER NOT NULL CHECK(range_days BETWEEN 1 AND 365), PRIMARY KEY(shop_id,module))""")
    db.execute("""INSERT INTO shop_auto_sync_settings(shop_id,module,enabled,interval_hours,range_days)
      SELECT shop_id,module,enabled,interval_hours,range_days FROM shop_auto_sync_settings_v10""")
    db.execute("""INSERT INTO shop_auto_sync_settings(shop_id,module,enabled,interval_hours,range_days)
      SELECT id,'finance_transactions',0,24,31 FROM shops
      WHERE NOT EXISTS (SELECT 1 FROM shop_auto_sync_settings s
                        WHERE s.shop_id=shops.id AND s.module='finance_transactions')""")
    db.execute("DROP TABLE shop_auto_sync_settings_v10")
    _create_finance_tables(db)
    db.execute("PRAGMA user_version=11")


def _migrate_v11_to_v12(db):
    _create_erp_cost_tables(db)
    db.execute("PRAGMA user_version=12")


def _migrate_v12_to_v13(db):
    db.execute("DROP TABLE IF EXISTS product_forecast_cost_history")
    db.execute("DROP TABLE IF EXISTS product_forecast_costs")
    db.execute("PRAGMA user_version=13")


def init_db():
    with transaction() as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        populated = db.execute("""SELECT 1 FROM sqlite_master
          WHERE type IN ('table','index') AND name NOT LIKE 'sqlite_%' LIMIT 1""").fetchone()
        if populated:
            if version == 1:
                _migrate_v1_to_v2(db)
                version = 2
            if version == 2:
                _migrate_v2_to_v3(db)
                version = 3
            if version == 3:
                _migrate_v3_to_v4(db)
                version = 4
            if version == 4:
                _migrate_v4_to_v5(db)
                version = 5
            if version == 5:
                _migrate_v5_to_v6(db)
                version = 6
            if version == 6:
                _migrate_v6_to_v7(db)
                version = 7
            if version == 7:
                _migrate_v7_to_v8(db)
                version = 8
            if version == 8:
                _migrate_v8_to_v9(db)
                version = 9
            if version == 9:
                _migrate_v9_to_v10(db)
                version = 10
            if version == 10:
                _migrate_v10_to_v11(db)
                version = 11
            if version == 11:
                _migrate_v11_to_v12(db)
                version = 12
            if version == 12:
                _migrate_v12_to_v13(db)
                version = 13
            if version != SCHEMA_VERSION:
                raise RuntimeError(f"数据库结构版本不兼容（当前 {version}，需要 {SCHEMA_VERSION}）；请备份后重建数据库")
            return
        if version not in (0, SCHEMA_VERSION):
            raise RuntimeError(f"数据库结构版本不兼容（当前 {version}，需要 {SCHEMA_VERSION}）；请重建数据库")
        db.executescript(f"""
        CREATE TABLE shops (
          id INTEGER PRIMARY KEY CHECK(id IN (1,2)), name TEXT NOT NULL UNIQUE CHECK(trim(name)<>''),
          settlement_currency TEXT NOT NULL CHECK(settlement_currency IN ('USD','CNY')));
        INSERT INTO shops VALUES (1,'店铺1','USD'),(2,'店铺2','CNY');
        CREATE TABLE exchange_rates (
          from_currency TEXT NOT NULL CHECK(from_currency IN ('USD','CNY')),
          to_currency TEXT NOT NULL CHECK(to_currency='RUB'), valid_from_utc TEXT NOT NULL,
          valid_to_utc TEXT NOT NULL, service_penalty_exchange_rate TEXT NOT NULL,
          sales_exchange_rate TEXT,
          source TEXT NOT NULL DEFAULT 'ozon_xapi' CHECK(source='ozon_xapi'), fetched_at TEXT NOT NULL,
          PRIMARY KEY(from_currency,to_currency,valid_from_utc,valid_to_utc));
        CREATE TABLE import_batches (
          id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER NOT NULL REFERENCES shops(id),
          kind TEXT NOT NULL, filename TEXT NOT NULL,
          imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          row_count INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE orders (
          shop_id INTEGER NOT NULL REFERENCES shops(id), posting_number TEXT NOT NULL,
          parent_order_no TEXT, channel TEXT NOT NULL CHECK(channel IN ('FBP','realFBS','WHD')),
          created_at TEXT, shipped_at TEXT, delivered_at TEXT, tracking_number TEXT,
          status_raw TEXT NOT NULL DEFAULT '', cancel_reason_raw TEXT, cancel_reason_id TEXT,
          shipped INTEGER NOT NULL DEFAULT 0 CHECK(shipped IN (0,1)),
          cancelled_after_ship INTEGER CHECK(cancelled_after_ship IN (0,1)),
          data_anomaly INTEGER NOT NULL DEFAULT 0 CHECK(data_anomaly IN (0,1)),
          amount_original REAL, amount_currency TEXT, buyer_paid REAL, buyer_currency TEXT,
          warehouse_id TEXT, status_changed_at TEXT, source TEXT NOT NULL,
          import_batch_id INTEGER REFERENCES import_batches(id),
          updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          PRIMARY KEY(shop_id,posting_number));
        CREATE TABLE order_items (
          shop_id INTEGER NOT NULL, channel TEXT NOT NULL, posting_number TEXT NOT NULL,
          sku TEXT NOT NULL, offer_id TEXT, product_name_raw TEXT NOT NULL DEFAULT '',
          quantity INTEGER NOT NULL CHECK(quantity>0), unit_price REAL, price_currency TEXT,
          buyer_paid REAL, buyer_currency TEXT, source TEXT NOT NULL,
          import_batch_id INTEGER REFERENCES import_batches(id),
          PRIMARY KEY(shop_id,posting_number,sku),
          FOREIGN KEY(shop_id,posting_number) REFERENCES orders(shop_id,posting_number));
        CREATE TABLE sync_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER NOT NULL REFERENCES shops(id),
          module TEXT NOT NULL, range_from TEXT, range_to TEXT,
          started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          finished_at TEXT, data_through TEXT, status TEXT NOT NULL, error TEXT,
          progress_done INTEGER NOT NULL DEFAULT 0, progress_total INTEGER NOT NULL DEFAULT 1,
          records INTEGER NOT NULL DEFAULT 0, current_from TEXT, current_to TEXT,
          run_source TEXT NOT NULL DEFAULT 'manual', scheduled_slot TEXT);
        CREATE TABLE return_records (
          shop_id INTEGER NOT NULL REFERENCES shops(id), record_key TEXT NOT NULL,
          occurred_at TEXT, posting_number TEXT, sku TEXT, payload TEXT NOT NULL, fetched_at TEXT NOT NULL,
          PRIMARY KEY(shop_id,record_key));
        CREATE TABLE rfbs_return_records (
          shop_id INTEGER NOT NULL REFERENCES shops(id), return_id INTEGER NOT NULL,
          return_number TEXT NOT NULL CHECK(trim(return_number)<>''), created_at TEXT,
          posting_number TEXT, offer_id TEXT, sku TEXT, product_name TEXT, status_raw TEXT,
          status_name TEXT, payload TEXT NOT NULL, fetched_at TEXT NOT NULL, order_number TEXT,
          quantity INTEGER, reason_raw TEXT, reason_name TEXT, compensation_status TEXT,
          product_amount REAL, product_currency TEXT, logistic_return_at TEXT,
          buyer_comment_raw TEXT, detail_fetched_at TEXT, PRIMARY KEY(shop_id,return_id));
        CREATE TABLE stock_snapshots (
          shop_id INTEGER NOT NULL REFERENCES shops(id), record_key TEXT NOT NULL,
          observed_at TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(shop_id,record_key));
        CREATE TABLE notification_settings (
          id INTEGER PRIMARY KEY CHECK(id=1),
          daily_enabled INTEGER NOT NULL DEFAULT 0 CHECK(daily_enabled IN (0,1)),
          push_time TEXT NOT NULL DEFAULT '09:00', weekdays TEXT NOT NULL DEFAULT '1,2,3,4,5,6,7',
          template TEXT NOT NULL);
        INSERT INTO notification_settings VALUES(1,0,'09:00','1,2,3,4,5,6,7','{{{{统计日期}}}} 取消与退货订单汇总

{{{{店铺明细}}}}');
        CREATE TABLE notification_runs (
          kind TEXT NOT NULL, stats_date TEXT NOT NULL, status TEXT NOT NULL,
          attempted_at TEXT NOT NULL, sent_at TEXT, error TEXT, PRIMARY KEY(kind,stats_date));
        CREATE TABLE complaints (
          shop_id INTEGER NOT NULL REFERENCES shops(id), complaint_number TEXT NOT NULL,
          posting_number TEXT NOT NULL, complaint_at TEXT NOT NULL, channel TEXT NOT NULL,
          resolved INTEGER CHECK(resolved IN (0,1) OR resolved IS NULL),
          package_returned INTEGER CHECK(package_returned IN (0,1) OR package_returned IS NULL),
          compensation_amount REAL, compensation_currency TEXT, notes TEXT,
          not_received_return INTEGER CHECK(not_received_return IN (0,1) OR not_received_return IS NULL),
          warehouse TEXT, order_process_status TEXT, complaint_status TEXT, compensation_status TEXT,
          platform_compensation_rub TEXT, platform_compensated_at TEXT,
          logistics_compensation_cny TEXT, logistics_compensated_at TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          PRIMARY KEY(shop_id,complaint_number,posting_number),
          FOREIGN KEY(shop_id,posting_number) REFERENCES orders(shop_id,posting_number));
        CREATE TABLE rfbs_return_disputes (
          shop_id INTEGER NOT NULL REFERENCES shops(id), return_number TEXT NOT NULL,
          refund_type TEXT, refund_amount REAL, refund_currency TEXT,
          platform_compensation REAL, platform_compensation_currency TEXT, process_status TEXT,
          return_method TEXT, iml_return_number TEXT, iml_system_sn TEXT, buyer_tracking_number TEXT,
          handling_method TEXT, video_recorded INTEGER CHECK(video_recorded IN (0,1) OR video_recorded IS NULL),
          outbound_order_number TEXT, return_result TEXT, notes TEXT,
          platform_compensation_rub TEXT, platform_compensated_at TEXT,
          logistics_compensation_cny TEXT, logistics_compensated_at TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(shop_id,return_number));
        CREATE TABLE product_short_names (
          key_type TEXT NOT NULL CHECK(key_type='sku'), key_value TEXT NOT NULL,
          short_name TEXT NOT NULL CHECK(trim(short_name)<>''), updated_at TEXT NOT NULL,
          PRIMARY KEY(key_type,key_value));
        CREATE TABLE product_groups (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE CHECK(trim(name)<>''),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE product_group_members (
          group_id INTEGER NOT NULL REFERENCES product_groups(id) ON DELETE CASCADE,
          key_type TEXT NOT NULL CHECK(key_type IN ('sku','offer_id')), key_value TEXT NOT NULL,
          PRIMARY KEY(key_type,key_value), UNIQUE(group_id,key_type,key_value));
        CREATE TABLE product_group_config (
          group_id INTEGER PRIMARY KEY REFERENCES product_groups(id) ON DELETE CASCADE,
          primary_offer_id TEXT, primary_sku TEXT, status TEXT NOT NULL DEFAULT 'pending',
          note TEXT NOT NULL DEFAULT '');
        CREATE TABLE shop_auto_sync_settings (
          shop_id INTEGER NOT NULL REFERENCES shops(id),
          module TEXT NOT NULL CHECK(module IN (
            'orders','returns','stock','ad_campaign_daily','ad_sku_daily','finance_transactions')),
          enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
          interval_hours INTEGER NOT NULL DEFAULT 24 CHECK(interval_hours IN (1,2,3,4,6,8,12,24)),
          range_days INTEGER NOT NULL CHECK(range_days BETWEEN 1 AND 365), PRIMARY KEY(shop_id,module));
        INSERT INTO shop_auto_sync_settings VALUES
          (1,'orders',0,24,3),(1,'returns',0,24,3),(1,'stock',0,24,1),
          (2,'orders',0,24,3),(2,'returns',0,24,3),(2,'stock',0,24,1),
          (1,'ad_campaign_daily',0,24,7),(1,'ad_sku_daily',0,24,7),
          (2,'ad_campaign_daily',0,24,7),(2,'ad_sku_daily',0,24,7),
          (1,'finance_transactions',0,24,31),(2,'finance_transactions',0,24,31);
        CREATE TABLE stock_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT, shop_id INTEGER NOT NULL REFERENCES shops(id),
          source TEXT NOT NULL, warehouse_id TEXT, sku TEXT NOT NULL, present INTEGER NOT NULL,
          reserved INTEGER NOT NULL, occurred_at TEXT NOT NULL, event_key TEXT, payload_json TEXT NOT NULL,
          UNIQUE(shop_id,source,event_key,warehouse_id,sku));
        CREATE TABLE ozon_webhook_events (
          event_key TEXT NOT NULL, shop_id INTEGER NOT NULL REFERENCES shops(id),
          message_type TEXT NOT NULL, posting_number TEXT, order_number TEXT,
          occurred_at TEXT, payload_json TEXT NOT NULL, received_at TEXT NOT NULL,
          applied_at TEXT, error TEXT, PRIMARY KEY(shop_id,event_key));
        CREATE TABLE ad_campaigns (
          shop_id INTEGER NOT NULL REFERENCES shops(id), campaign_id TEXT NOT NULL,
          name TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '',
          payment_type TEXT, adv_object_type TEXT, placement TEXT,
          weekly_budget REAL, created_at TEXT, updated_at TEXT,
          synced_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
          PRIMARY KEY(shop_id,campaign_id));
        CREATE INDEX idx_orders_created ON orders(shop_id,created_at);
        CREATE INDEX idx_orders_cancelled ON orders(shop_id,status_raw,shipped,created_at);
        CREATE INDEX idx_items_sku ON order_items(shop_id,sku);
        CREATE INDEX idx_complaints_order ON complaints(shop_id,posting_number);
        CREATE INDEX idx_stock_history_time ON stock_history(shop_id,occurred_at);
        CREATE INDEX idx_ozon_webhook_events_posting
          ON ozon_webhook_events(shop_id,posting_number,occurred_at);
        CREATE INDEX idx_ozon_webhook_events_pending
          ON ozon_webhook_events(shop_id,applied_at,occurred_at);
        CREATE UNIQUE INDEX idx_auto_sync_once ON sync_runs(shop_id,module,scheduled_slot)
          WHERE run_source='auto' AND status IN ('running','success') AND scheduled_slot IS NOT NULL;
        CREATE UNIQUE INDEX idx_sync_one_running ON sync_runs(shop_id,module)
          WHERE status='running';
        PRAGMA user_version={SCHEMA_VERSION};
        PRAGMA optimize;
        """)
        _create_ad_statistics(db)
        _create_alert_tables(db)
        _create_finance_tables(db)
        _create_erp_cost_tables(db)
