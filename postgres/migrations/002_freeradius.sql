BEGIN;

CREATE TABLE IF NOT EXISTS radcheck (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username VARCHAR(64) NOT NULL DEFAULT '',
  attribute VARCHAR(64) NOT NULL DEFAULT '',
  op CHAR(2) NOT NULL DEFAULT '==',
  value VARCHAR(253) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS radreply (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username VARCHAR(64) NOT NULL DEFAULT '',
  attribute VARCHAR(64) NOT NULL DEFAULT '',
  op CHAR(2) NOT NULL DEFAULT '=',
  value VARCHAR(253) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS radgroupcheck (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  groupname VARCHAR(64) NOT NULL DEFAULT '',
  attribute VARCHAR(64) NOT NULL DEFAULT '',
  op CHAR(2) NOT NULL DEFAULT '==',
  value VARCHAR(253) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS radgroupreply (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  groupname VARCHAR(64) NOT NULL DEFAULT '',
  attribute VARCHAR(64) NOT NULL DEFAULT '',
  op CHAR(2) NOT NULL DEFAULT '=',
  value VARCHAR(253) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS radusergroup (
  username VARCHAR(64) NOT NULL DEFAULT '',
  groupname VARCHAR(64) NOT NULL DEFAULT '',
  priority INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (username, groupname)
);

CREATE TABLE IF NOT EXISTS radacct (
  radacctid BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  acctsessionid VARCHAR(64) NOT NULL DEFAULT '',
  acctuniqueid VARCHAR(64) NOT NULL,
  username VARCHAR(64) NOT NULL DEFAULT '',
  groupname VARCHAR(64),
  realm VARCHAR(64),
  nasipaddress INET NOT NULL,
  nasportid VARCHAR(32),
  nasporttype VARCHAR(32),
  acctstarttime TIMESTAMPTZ,
  acctupdatetime TIMESTAMPTZ,
  acctstoptime TIMESTAMPTZ,
  acctdelaytime BIGINT,
  acctinterval BIGINT,
  acctsessiontime BIGINT,
  acctauthentic VARCHAR(32),
  connectinfo_start VARCHAR(128),
  connectinfo_stop VARCHAR(128),
  acctinputgigawords BIGINT,
  acctinputoctets BIGINT,
  acctoutputgigawords BIGINT,
  acctoutputoctets BIGINT,
  calledstationid VARCHAR(64),
  callingstationid VARCHAR(64),
  acctterminatecause VARCHAR(32),
  servicetype VARCHAR(32),
  framedprotocol VARCHAR(32),
  framedipaddress INET,
  framedipv6address INET,
  framedipv6prefix INET,
  framedinterfaceid VARCHAR(64),
  delegatedipv6prefix INET,
  class TEXT,
  CONSTRAINT radacct_acctuniqueid_unique UNIQUE (acctuniqueid)
);

ALTER TABLE radacct ADD COLUMN IF NOT EXISTS acctdelaytime BIGINT;
ALTER TABLE radacct ADD COLUMN IF NOT EXISTS acctinputgigawords BIGINT;
ALTER TABLE radacct ADD COLUMN IF NOT EXISTS acctoutputgigawords BIGINT;
ALTER TABLE radacct ADD COLUMN IF NOT EXISTS framedinterfaceid VARCHAR(64);

CREATE TABLE IF NOT EXISTS radpostauth (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username VARCHAR(64) NOT NULL DEFAULT '',
  pass VARCHAR(128),
  reply VARCHAR(32),
  class TEXT,
  authdate TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE radpostauth ADD COLUMN IF NOT EXISTS class TEXT;

CREATE INDEX IF NOT EXISTS idx_radcheck_username ON radcheck (username);
CREATE INDEX IF NOT EXISTS idx_radreply_username ON radreply (username);
CREATE INDEX IF NOT EXISTS idx_radgroupcheck_groupname ON radgroupcheck (groupname);
CREATE INDEX IF NOT EXISTS idx_radgroupreply_groupname ON radgroupreply (groupname);
CREATE INDEX IF NOT EXISTS idx_radusergroup_username ON radusergroup (username);

CREATE INDEX IF NOT EXISTS idx_radacct_username ON radacct (username);
CREATE INDEX IF NOT EXISTS idx_radacct_framedipaddress ON radacct (framedipaddress);
CREATE INDEX IF NOT EXISTS idx_radacct_callingstationid ON radacct (callingstationid);
CREATE INDEX IF NOT EXISTS idx_radacct_acctstarttime ON radacct (acctstarttime);
CREATE INDEX IF NOT EXISTS idx_radacct_acctstoptime ON radacct (acctstoptime);
CREATE INDEX IF NOT EXISTS idx_radacct_nasipaddress ON radacct (nasipaddress);

CREATE INDEX IF NOT EXISTS idx_radpostauth_username ON radpostauth (username);
CREATE INDEX IF NOT EXISTS idx_radpostauth_authdate ON radpostauth (authdate);

COMMIT;
