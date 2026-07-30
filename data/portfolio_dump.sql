PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;

CREATE TABLE holdings (
    ticker TEXT NOT NULL,
    company TEXT,
    shares REAL NOT NULL,
    sector TEXT,
    broker TEXT DEFAULT 'BECA Vestiva',
    cedear_ratio REAL,
    is_cedear INTEGER DEFAULT 0,
    is_crypto INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (ticker, broker)
);

INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('AMD','Advanced Micro Devices',24.0,'Semiconductores','BECA Vestiva',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('AMZN','Amazon.com Inc',3.0,'Venta Minorista','BECA Vestiva',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('AVGO','Broadcom Inc',9.0,'Semiconductores','BECA Vestiva',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('GOOG','Google (Alphabet Inc Class C)',4.0,'Medios de Comunicación','BECA Vestiva',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('INTC','Intel Corp',24.0,'Semiconductores','BECA Vestiva',NULL,0,0,'2026-07-23 23:42:28');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('META','Meta Platforms Inc',2.0,'Medios de Comunicación','BECA Vestiva',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('MSFT','Microsoft Corp',1.0,'Tecnología','BECA Vestiva',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('MU','Micron Technology Inc',14.0,'Tecnología','BECA Vestiva',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('NU','NU HOLDINGS LTD',199.0,'Servicios Financieros','BECA Vestiva',NULL,0,0,'2026-07-23 23:42:28');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('PAM','Pampa Energia SA',15.0,'Utilidad Pública','BECA Vestiva',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('PLTR','Palantir Technologies',24.0,'Tecnología','BECA Vestiva',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('QCOM','Qualcomm Inc',11.0,'Semiconductores','BECA Vestiva',NULL,0,0,'2026-07-23 23:42:35');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('YPF','YPF S.A.',98.0,'Energía','BECA Vestiva',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('ALUA','ALUA',154.0,NULL,'TM Inversiones',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('CEPU','CEPU',167.0,NULL,'TM Inversiones',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('ECOG','ECOG',8.0,NULL,'TM Inversiones',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('PAMP','PAMP',110.0,NULL,'TM Inversiones',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('TGNO4','TGNO4',90.0,NULL,'TM Inversiones',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('YPFD','YPFD',12.0,NULL,'TM Inversiones',NULL,0,0,NULL);
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('AMD','Advanced Micro Devices',30.0,'Semiconductores','TM Inversiones',NULL,1,0,'2026-07-21 17:18:54');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('ARKK','ARK Innovation ETF',29.0,'ETF','TM Inversiones',NULL,1,0,'2026-07-21 17:18:54');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('GOOGL','Google (Alphabet Inc)',109.0,'Medios de Comunicación','TM Inversiones',NULL,1,0,'2026-07-21 17:18:54');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('INTC','Intel Corp',23.0,'Semiconductores','TM Inversiones',NULL,1,0,'2026-07-21 17:18:54');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('MRVL','Marvell Technology',350.0,'Semiconductores','TM Inversiones',NULL,1,0,'2026-07-21 17:18:54');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('MSFT','Microsoft Corp',11.0,'Tecnología','TM Inversiones',NULL,1,0,'2026-07-21 17:18:54');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('XYZ','XYZ',50.0,'','TM Inversiones',NULL,1,0,'2026-07-21 17:18:54');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('PAMP','Pampa Energia SA',176.0,'Utilidad Pública','Balanz',NULL,0,0,'2026-07-21 17:26:24');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('ALAB','CEDEAR ASTERA LABS INC',98.0,'Tecnología','Balanz',NULL,1,0,'2026-07-21 17:26:24');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('ARM','ARM HOLDINGS PLC',40.0,'Semiconductores','Balanz',NULL,1,0,'2026-07-21 17:26:24');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('ASTS','CEDEAR AST SPACEMOBILE INC',59.0,'Telecomunicaciones','Balanz',NULL,1,0,'2026-07-21 17:26:24');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('MRVL','CEDEAR MARVELL TECHNOLOGY INC',80.0,'Semiconductores','Balanz',NULL,1,0,'2026-07-21 17:26:24');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('MSFT','CEDEAR MICROSOFT CORP',48.0,'Tecnología','Balanz',NULL,1,0,'2026-07-21 17:26:24');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('MU','CEDEAR MICRON TECHNOLOGY INC',5.0,'Semiconductores','Balanz',NULL,1,0,'2026-07-21 17:26:24');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('RKLB','CEDEAR ROCKET LAB CORP',54.0,'Aeroespacial','Balanz',NULL,1,0,'2026-07-21 17:26:24');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('BTC','Bitcoin',0.04080453,'Cryptocurrency','Belo',NULL,0,1,'2026-07-21 17:28:13');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('ETH','Ethereum',0.0553906,'Cryptocurrency','Belo',NULL,0,1,'2026-07-21 17:28:13');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('VIST','Vista Energy SAB de CV',12.0,'Energía','BECA Vestiva',NULL,0,0,'2026-07-23 23:42:28');
INSERT INTO holdings (ticker,company,shares,sector,broker,cedear_ratio,is_cedear,is_crypto,updated_at) VALUES ('IBM','International Business Machines Corp',18.0,'Tecnología','Balanz',NULL,1,0,'2026-07-23 23:44:59');

CREATE TABLE prices (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL, price REAL NOT NULL, currency TEXT DEFAULT 'USD', recorded_at TEXT DEFAULT (datetime('now')), is_cedear INTEGER DEFAULT 0);

INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (1,'AMD',541.52,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (2,'AMZN',248.045,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (3,'AVGO',386.08,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (4,'GOOG',348.19,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (5,'INTC',105.14,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (6,'META',646.32,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (7,'MSFT',398.47,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (8,'MU',975.59,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (9,'NU',14.285,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (10,'PAM',86.54,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (11,'PLTR',132.81,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (12,'QCOM',173.08,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (13,'YPF',51.26,'USD','2026-07-21 17:14:24');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (14,'PAM',86.86000061035156,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (15,'QCOM',150.97000122070312,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (16,'YPFD',80600.0,'ARS','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (17,'META',533.4205932617188,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (18,'CEPU',2396.0,'ARS','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (19,'MU',858.7999877929688,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (20,'AMZN',237.6300048828125,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (21,'ALUA',970.0,'ARS','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (22,'NU',14.164999961853027,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (23,'GOOG',332.6199951171875,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (24,'AMD',495.3550109863281,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (25,'AVGO',387.3399963378906,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (26,'TGNO4',4010.0,'ARS','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (27,'ECOG',3007.5,'ARS','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (28,'PAMP',5465.0,'ARS','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (29,'PLTR',121.42500305175781,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (30,'MSFT',450.30999755859375,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (31,'YPF',51.41999816894531,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (32,'INTC',93.2699966430664,'USD','2026-07-30 14:41:08');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (33,'TGNO4',4010.0,'ARS','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (34,'GOOG',332.760009765625,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (35,'ECOG',3020.0,'ARS','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (36,'AMZN',237.77999877929688,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (37,'ALUA',971.5,'ARS','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (38,'MU',859.2869873046875,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (39,'YPF',51.415000915527344,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (40,'AVGO',387.6199951171875,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (41,'INTC',93.30000305175781,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (42,'QCOM',151.14999389648438,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (43,'MSFT',450.3900146484375,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (44,'PAM',86.3550033569336,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (45,'NU',14.149999618530273,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (46,'AMD',495.5963134765625,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (47,'PLTR',121.37999725341797,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (48,'YPFD',80600.0,'ARS','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (49,'META',533.1799926757812,'USD','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (50,'PAMP',5465.0,'ARS','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (51,'CEPU',2387.0,'ARS','2026-07-30 14:41:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (52,'CEPU',2395.0,'ARS','2026-07-30 14:42:42');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (53,'TGNO4',4047.5,'ARS','2026-07-30 14:42:42');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (54,'IBM',222.289306640625,'USD','2026-07-30 14:42:42');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (55,'ECOG',3020.0,'ARS','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (56,'AMD',495.43499755859375,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (57,'ALAB',289.0150146484375,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (58,'PAMP',5475.0,'ARS','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (59,'PAM',86.44999694824219,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (60,'ARM',241.64999389648438,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (61,'GOOGL',333.364990234375,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (62,'ASTS',57.79499816894531,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (63,'PLTR',121.27999877929688,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (64,'QCOM',151.02999877929688,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (65,'INTC',93.26480102539062,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (66,'BTC',64758.62109375,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (67,'ARKK',72.51000213623047,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (68,'META',532.7999877929688,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (69,'GOOG',332.7099914550781,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (70,'MSFT',451.82000732421875,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (71,'RKLB',63.88999938964844,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (72,'ETH',1919.0400390625,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (73,'NU',14.15999984741211,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (74,'VIST',66.76499938964844,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (75,'MRVL',183.58999633789062,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (76,'AVGO',387.0,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (77,'YPF',51.415000915527344,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (78,'ALUA',970.0,'ARS','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (79,'AMZN',237.38999938964844,'USD','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (80,'YPFD',80400.0,'ARS','2026-07-30 14:42:43');
INSERT INTO prices (id,ticker,price,currency,recorded_at) VALUES (81,'MU',857.5869750976562,'USD','2026-07-30 14:42:43');

COMMIT;
